// 정적 배포 디렉터리에서 임시 실험 자산만 뺀다. 로컬 public/ 파일은 유지한다.
import { existsSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

if (process.env.GUIDE_EXPERIMENTS === "1" && process.env.DEV_TOOLS === "1") {
  console.log("[guide] 실험을 명시적으로 켠 빌드: 눈썹 인식 자산을 유지합니다");
} else {
  for (const relative of [
    "brow-runtime",
    "models/brow-resnet18.onnx",
    "fixtures/guides/compare-baseline.json",
    "fixtures/guides/compare-candidate.json",
  ]) {
    const path = fileURLToPath(new URL(`../out/${relative}`, import.meta.url));
    if (existsSync(path)) rmSync(path, { recursive: true, force: true });
  }
  console.log("[guide] 배포 결과물에서 임시 눈썹 모델·WASM·비교 픽스처를 제외했습니다");
}
