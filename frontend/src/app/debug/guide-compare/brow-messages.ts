export type BrowRequest = { type: "init" } | { type: "detect"; id: number; input: Float32Array };

export type BrowResponse =
  | { type: "ready" }
  | { type: "result"; id: number; mask: Uint8Array; ms: number }
  | { type: "error"; id?: number; message: string };
