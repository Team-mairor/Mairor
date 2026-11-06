// 개발 눈썹 비교 화면 전용. Node 22.18+; npm run brow:assets
import { createHash } from "node:crypto";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { fileURLToPath } from "node:url";
const path = (value) => fileURLToPath(new URL(value, import.meta.url));
const expected = "0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f";
const model = path("../public/models/brow-resnet18.onnx");
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
mkdirSync(path("../public/models/"), { recursive: true });
if (!existsSync(model) || hash(readFileSync(model)) !== expected) {
  console.log("[brow] 얼굴 부위 분할 모델을 내려받습니다 (약 53 MB)");
  const response = await fetch(
    "https://github.com/yakhyo/face-parsing/releases/download/v0.0.1/resnet18.onnx",
    { signal: AbortSignal.timeout(120000) },
  );
  if (!response.ok) throw new Error(`모델 다운로드 실패: ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (hash(bytes) !== expected) throw new Error("눈썹 모델 SHA-256 불일치");
  writeFileSync(`${model}.tmp`, bytes);
  renameSync(`${model}.tmp`, model);
}
mkdirSync(path("../public/brow-runtime/"), { recursive: true });
for (const name of ["ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.wasm"])
  copyFileSync(
    path(`../node_modules/onnxruntime-web/dist/${name}`),
    path(`../public/brow-runtime/${name}`),
  );
console.log("[brow] 브라우저 눈썹 인식 파일을 준비했습니다");
