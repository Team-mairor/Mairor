import type { CellSampler } from "./cells";
import type { EyeSampler } from "./white";

/** 칸 · 눈 구멍 표본 자리. 얼굴 지도로 정해져 한 번만 만든다 */
export interface Samplers {
  cells: CellSampler;
  eyes: EyeSampler;
}
