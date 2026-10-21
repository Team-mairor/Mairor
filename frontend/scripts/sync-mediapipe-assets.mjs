// MediaPipe wasm(설치된 tasks-vision과 버전이 같아야 함)과 공유 모델을 public/으로 복사한다.
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
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

console.log("[sync-mediapipe-assets] MediaPipe wasm·모델 파일을 public/에 복사했습니다.");
