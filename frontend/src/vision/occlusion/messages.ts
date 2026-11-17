export type OcclusionProvider = "webgpu" | "wasm";

export type OcclusionRequest =
  | { type: "init"; provider: OcclusionProvider }
  | { type: "run"; id: number; size: number; input: Float32Array };

export type OcclusionResponse =
  | {
      type: "ready";
      provider: OcclusionProvider;
      ms: number;
      inputName: string;
      outputName: string;
    }
  | {
      type: "result";
      id: number;
      /** 픽셀마다 가림이면 1 (size × size) */
      mask: Uint8Array;
      /** 모델을 돌린 시간과 출력에서 가림 라벨을 고르는 시간(ms) */
      runMs: number;
      postMs: number;
    }
  | { type: "error"; id?: number; message: string };
