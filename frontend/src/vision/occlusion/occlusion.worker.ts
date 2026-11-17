import {
  OCCLUSION_CLASSES,
  OCCLUSION_LABEL,
  OCCLUSION_MODEL_URL,
  OCCLUSION_RUNTIME_PATH,
} from "./constants";
import type { OcclusionProvider, OcclusionRequest, OcclusionResponse } from "./messages";

type Ort = typeof import("onnxruntime-web");

const send = (message: OcclusionResponse, transfer: Transferable[] = []) =>
  self.postMessage(message, { transfer });

let ort: Ort | null = null;
let session: import("onnxruntime-web").InferenceSession | null = null;
let inputName = "";
let outputName = "";

async function init(provider: OcclusionProvider) {
  // 빌드가 두 실행 파일을 따로 묶도록 필요한 쪽만 불러온다
  ort = (
    provider === "webgpu"
      ? await import("onnxruntime-web/webgpu")
      : await import("onnxruntime-web/wasm")
  ) as Ort;
  ort.env.wasm.wasmPaths = OCCLUSION_RUNTIME_PATH;
  // 교차 출처 격리가 없어 여러 스레드를 못 쓴다
  ort.env.wasm.numThreads = 1;
  const started = performance.now();
  session = await ort.InferenceSession.create(OCCLUSION_MODEL_URL, {
    executionProviders: [provider],
  });
  inputName = session.inputNames[0];
  outputName = session.outputNames[0];
  send({ type: "ready", provider, ms: performance.now() - started, inputName, outputName });
}

async function run(id: number, size: number, input: Float32Array) {
  if (!ort || !session) throw new Error("모델이 아직 준비되지 않았습니다");
  const tensor = new ort.Tensor("float32", input, [1, 3, size, size]);
  let results: Awaited<ReturnType<typeof session.run>> | null = null;
  try {
    const started = performance.now();
    results = await session.run({ [inputName]: tensor });
    const output = results[outputName];
    const dims = output.dims;
    if (dims.length !== 4 || dims[1] !== OCCLUSION_CLASSES || dims[2] !== size || dims[3] !== size)
      throw new Error(`가림 모델 출력 모양이 맞지 않습니다: ${dims.join("x")}`);
    // WebGPU는 출력이 GPU에 있어 읽어 오는 시간까지 모델 시간에 넣는다
    const values = (await output.getData()) as Float32Array;
    const runMs = performance.now() - started;

    const postStarted = performance.now();
    const pixels = size * size;
    const mask = new Uint8Array(pixels);
    for (let i = 0; i < pixels; i++) {
      let best = -Infinity;
      let label = 0;
      for (let c = 0; c < OCCLUSION_CLASSES; c++) {
        const v = values[c * pixels + i];
        if (v > best) {
          best = v;
          label = c;
        }
      }
      if (label === OCCLUSION_LABEL) mask[i] = 1;
    }
    send({ type: "result", id, mask, runMs, postMs: performance.now() - postStarted }, [
      mask.buffer,
    ]);
  } finally {
    tensor.dispose();
    Object.values(results ?? {}).forEach((t) => t.dispose());
  }
}

self.onmessage = async (event: MessageEvent<OcclusionRequest>) => {
  const message = event.data;
  try {
    if (message.type === "init") await init(message.provider);
    else await run(message.id, message.size, message.input);
  } catch (error) {
    send({
      type: "error",
      id: message.type === "run" ? message.id : undefined,
      message: error instanceof Error ? error.message : String(error),
    });
  }
};
