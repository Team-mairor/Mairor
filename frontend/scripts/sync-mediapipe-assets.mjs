// MediaPipe wasm(설치된 tasks-vision과 버전이 같아야 함)과 공유 모델을 public/으로 복사한다.
// 공유하지 않는 모델은 저장소에 두지 않고 공식 주소에서 받아 SHA-256으로 확인한다.
// 받는 모델은 없어도 추적은 동작하는 부가 기능용이라, 받지 못하면 경고만 남기고 계속한다.
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), "..");

const copies = [
  {
    from: join(frontendDir, "node_modules/@mediapipe/tasks-vision/wasm"),
    to: join(frontendDir, "public/mediapipe/wasm"),
  },
  {
    from: join(frontendDir, "../shared/face-mesh/face_landmarker.task"),
    to: join(frontendDir, "public/models/face_landmarker.task"),
  },
];

const downloads = [
  {
    url: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    sha256: "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f",
    to: join(frontendDir, "public/models/blaze_face_short_range.tflite"),
  },
];

const DOWNLOAD_TIMEOUT_MS = 30_000;

const sha256 = (data) => createHash("sha256").update(data).digest("hex");

for (const { from, to } of copies) {
  if (!existsSync(from)) {
    console.error(`[sync-mediapipe-assets] 원본이 없습니다: ${from}`);
    process.exit(1);
  }

  if (from.endsWith(".task")) {
    mkdirSync(dirname(to), { recursive: true });
    copyFileSync(from, to);
  } else {
    mkdirSync(to, { recursive: true });
    for (const file of readdirSync(from)) {
      copyFileSync(join(from, file), join(to, file));
    }
  }
}

for (const { url, sha256: expected, to } of downloads) {
  // 이미 받은 파일이 맞으면 다시 받지 않는다.
  if (existsSync(to) && sha256(readFileSync(to)) === expected) continue;

  console.log(`[sync-mediapipe-assets] 내려받는 중: ${url}`);
  let data;
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) });
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
  mkdirSync(dirname(to), { recursive: true });
  writeFileSync(to, data);
}

console.log("[sync-mediapipe-assets] MediaPipe wasm·모델 파일을 public/에 준비했습니다.");
