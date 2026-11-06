import * as ort from "onnxruntime-web/wasm";

import type { BrowRequest, BrowResponse } from "./brow-messages";

const send = (message: BrowResponse, transfer: Transferable[] = []) =>
  self.postMessage(message, { transfer });

ort.env.wasm.wasmPaths = "/brow-runtime/";
ort.env.wasm.numThreads = 1;
let session: ort.InferenceSession | null = null;
self.onmessage = async (event: MessageEvent<BrowRequest>) => {
  try {
    if (!session) {
      session = await ort.InferenceSession.create("/models/brow-resnet18.onnx", {
        executionProviders: ["wasm"],
      });
      send({ type: "ready" });
    }
    if (event.data.type === "init") return;
    const start = performance.now();
    const input = new ort.Tensor("float32", event.data.input, [1, 3, 512, 512]);
    let results: ort.InferenceSession.ReturnType | null = null;
    try {
      results = await session.run({ [session.inputNames[0]]: input });
      const output = results[session.outputNames[0]],
        values = output.data as Float32Array;
      if (
        output.dims.length !== 4 ||
        output.dims[1] !== 19 ||
        output.dims[2] !== 512 ||
        output.dims[3] !== 512
      )
        throw new Error("눈썹 모델 출력 형식이 맞지 않습니다");
      const pixels = 512 * 512,
        mask = new Uint8Array(pixels);
      for (let i = 0; i < pixels; i++) {
        let best = -Infinity,
          label = 0;
        for (let c = 0; c < 19; c++)
          if (values[c * pixels + i] > best) {
            best = values[c * pixels + i];
            label = c;
          }
        if (label !== 2 && label !== 3) continue;
        let sum = 0;
        for (let c = 0; c < 19; c++) sum += Math.exp(values[c * pixels + i] - best);
        if (1 / sum >= 0.55) mask[i] = 1;
      }
      send({ type: "result", id: event.data.id, mask, ms: performance.now() - start }, [
        mask.buffer,
      ]);
    } finally {
      input.dispose();
      Object.values(results ?? {}).forEach((t) => t.dispose());
    }
  } catch (error) {
    send({
      type: "error",
      id: event.data.type === "detect" ? event.data.id : undefined,
      message: error instanceof Error ? error.message : String(error),
    });
  }
};
