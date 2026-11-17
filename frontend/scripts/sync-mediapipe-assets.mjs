// MediaPipe wasm·vision_bundle(설치된 tasks-vision과 버전이 같아야 함)과 얼굴 추론 Worker, 공유 모델·메시 파일을 public/으로 복사한다.
// 공유하지 않는 모델은 저장소에 두지 않고 공식 주소에서 받아 SHA-256으로 확인한다.
// 받는 모델은 없어도 추적은 동작하는 부가 기능용이라, 받지 못하면 경고만 남기고 계속한다.
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), "..");

const copies = [
  {
    from: join(frontendDir, "node_modules/@mediapipe/tasks-vision/vision_bundle.js"),
    to: join(frontendDir, "public/mediapipe/vision_bundle.js"),
  },
  {
    from: join(frontendDir, "scripts/face-worker.js"),
    to: join(frontendDir, "public/mediapipe/face-worker.js"),
  },
  {
    from: join(frontendDir, "node_modules/@mediapipe/tasks-vision/wasm"),
    to: join(frontendDir, "public/mediapipe/wasm"),
  },
  ...["face_landmarker.task", "triangles.v1.json", "uv.v1.json"].map((file) => ({
    from: join(frontendDir, "../shared/face-mesh", file),
    to: join(frontendDir, "public/models", file),
  })),
];

const downloads = [
  {
    url: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    sha256: "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f",
    to: join(frontendDir, "public/models/blaze_face_short_range.tflite"),
    timeoutMs: 30_000,
  },
  // shared/segmentation/README.md의 출처·SHA-256과 같아야 한다.
  {
    url: "https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite",
    sha256: "c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0",
    to: join(frontendDir, "public/models/selfie_multiclass_256x256.tflite"),
    // 16MB라 느린 회선에서도 받을 수 있게 넉넉히 둔다.
    timeoutMs: 120_000,
  },
];

const sha256 = (data) => createHash("sha256").update(data).digest("hex");

for (const { from, to } of copies) {
  if (!existsSync(from)) {
    console.error(`[sync-mediapipe-assets] 원본이 없습니다: ${from}`);
    process.exit(1);
  }

  if (statSync(from).isFile()) {
    mkdirSync(dirname(to), { recursive: true });
    copyFileSync(from, to);
  } else {
    mkdirSync(to, { recursive: true });
    for (const file of readdirSync(from)) {
      copyFileSync(join(from, file), join(to, file));
    }
  }
}

for (const { url, sha256: expected, to, timeoutMs } of downloads) {
  // 이미 받은 파일이 맞으면 다시 받지 않는다.
  if (existsSync(to)) {
    if (sha256(readFileSync(to)) === expected) continue;
    // 다시 받기도 실패하면 틀린 파일이 그대로 서빙되므로 먼저 지운다.
    rmSync(to);
  }

  console.log(`[sync-mediapipe-assets] 내려받는 중: ${url}`);
  let data;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = Buffer.from(await response.arrayBuffer());
  } catch (e) {
    console.warn(`[sync-mediapipe-assets] 내려받지 못해 건너뜁니다: ${url} (${e.message})`);
    continue;
  }
  const actual = sha256(data);
  if (actual !== expected) {
    console.warn(
      `[sync-mediapipe-assets] SHA-256이 달라 건너뜁니다: ${url}\n  기대 ${expected}\n  실제 ${actual}`,
    );
    continue;
  }
  // 쓰는 도중 멈춰도 잘린 파일이 남지 않도록 임시 파일에 쓴 뒤 옮긴다.
  mkdirSync(dirname(to), { recursive: true });
  writeFileSync(`${to}.tmp`, data);
  renameSync(`${to}.tmp`, to);
}

// 가림 찾기 모델(Git LFS)과 onnxruntime-web 실행 파일. shared/occlusion/README.md의 SHA-256과 같아야 한다.
// LFS 없이 받으면 130바이트 안팎의 포인터 파일이라, 개발에서는 경고만 하고 빌드에서는 멈춘다.
const occlusionModel = {
  from: join(frontendDir, "../shared/occlusion/occlusion_bisenet.v1.web.fp16.onnx"),
  to: join(frontendDir, "public/models/occlusion_bisenet.v1.web.fp16.onnx"),
  sha256: "8d9ef97b3d15585ad3803126235bebfd89c34a31518de8947207ca65e494e844",
};
// wasm 방식은 첫 두 개, WebGPU 방식은 브라우저가 지원하는 변형(asyncify · jspi · jsep) 가운데 하나를 불러온다
const ortFiles = [
  "ort-wasm-simd-threaded.mjs",
  "ort-wasm-simd-threaded.wasm",
  ...["asyncify", "jspi", "jsep"].flatMap((kind) => [
    `ort-wasm-simd-threaded.${kind}.mjs`,
    `ort-wasm-simd-threaded.${kind}.wasm`,
  ]),
];
const occlusionProblem = (() => {
  if (!existsSync(occlusionModel.from)) return "모델 파일이 없습니다";
  const data = readFileSync(occlusionModel.from);
  if (sha256(data) !== occlusionModel.sha256)
    return `SHA-256이 다릅니다(${data.length}바이트). Git LFS 포인터일 수 있으니 'git lfs pull'을 실행하세요`;
  mkdirSync(dirname(occlusionModel.to), { recursive: true });
  copyFileSync(occlusionModel.from, occlusionModel.to);
  return null;
})();
if (occlusionProblem) {
  const message = `[sync-mediapipe-assets] 가림 찾기 모델을 준비하지 못했습니다: ${occlusionProblem}`;
  if (process.env.npm_lifecycle_event === "prebuild") {
    console.error(message);
    process.exit(1);
  }
  console.warn(`${message}
  (개발 서버는 그대로 켜지지만 가림 찾기는 동작하지 않습니다)`);
}
const ortDist = join(frontendDir, "node_modules/onnxruntime-web/dist");
mkdirSync(join(frontendDir, "public/occlusion-runtime"), { recursive: true });
for (const name of ortFiles) {
  copyFileSync(join(ortDist, name), join(frontendDir, "public/occlusion-runtime", name));
}

console.log("[sync-mediapipe-assets] MediaPipe wasm·모델·메시 파일을 public/에 준비했습니다.");
