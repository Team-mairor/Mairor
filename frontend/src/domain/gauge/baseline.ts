import type { FaceFrame } from "@/vision/face";

import type { CellLab } from "./cells";
import { eyesOpen } from "./frame";
import { FRAMES, GRID, MEASURED } from "./spec";

/** 사진 한 장의 고개 각도(라디안)와 눈 뜬 정도(eyesOpen, 덜 뜬 쪽) */
export interface FrameQuality {
  yaw: number;
  pitch: number;
  roll: number;
  eyes: number;
}

export const qualityOf = (frame: FaceFrame): FrameQuality => ({
  ...frame.pose,
  eyes: eyesOpen(frame),
});

/** 고개가 정면인지. center가 있으면 그 사람의 위아래 정면도 함께 본다 */
export const frontPose = (q: FrameQuality, center: number | null = null) =>
  Math.abs(q.yaw) <= FRAMES.frontMax &&
  Math.abs(q.roll) <= FRAMES.rollMax &&
  (center === null || Math.abs(q.pitch - center) <= FRAMES.frontMax);

export const facing = (q: FrameQuality) => frontPose(q) && q.eyes >= FRAMES.eyesOpenMin;

/** 기준에 쓸 사진인지. 위아래 고개는 카메라 정면이 아니라 그 사람 정면(center)에서 본다 */
export const goodFrame = (q: FrameQuality, center: number) =>
  frontPose(q, center) && q.eyes >= FRAMES.eyesOpenMin;

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(mid)] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** 그 사람 정면 pitch. facing 조건을 지킨 앞 사진 pitchCenterFrames장의 가운데 값이다 */
export class FrontCenter {
  private pitches: number[];

  constructor(center?: number) {
    this.pitches = center === undefined ? [] : Array(FRAMES.pitchCenterFrames).fill(center);
  }

  push(q: FrameQuality) {
    if (this.pitches.length < FRAMES.pitchCenterFrames && facing(q)) this.pitches.push(q.pitch);
  }

  /** 아직 다 모으지 못했으면 null */
  get value(): number | null {
    return this.pitches.length < FRAMES.pitchCenterFrames ? null : median(this.pitches);
  }
}

/** 기준 하나. lab은 칸마다 가운데 값이고 색이 없는 칸은 NaN이다 */
export interface Baseline {
  lab: CellLab;
  /** 기준 색이 있는 칸 */
  cells: Uint8Array;
  frames: number;
}

/** 칸 색 표 여러 장의 칸마다 가운데 값(NaN 제외)으로 기준을 만든다. 맨얼굴 기준과 단계 시작 기준이 같은 방법이다 */
export function buildBaseline(grids: CellLab[]): Baseline {
  const lab = new Float32Array(GRID * GRID * 3).fill(NaN);
  const cells = new Uint8Array(GRID * GRID);
  const values: number[] = [];
  for (let k = 0; k < GRID * GRID; k++) {
    if (!MEASURED[k]) continue;
    let filled = true;
    for (let ch = 0; ch < 3; ch++) {
      values.length = 0;
      for (const grid of grids) {
        const v = grid[k * 3 + ch];
        if (!Number.isNaN(v)) values.push(v);
      }
      if (!values.length) {
        filled = false;
        break;
      }
      lab[k * 3 + ch] = median(values);
    }
    if (filled) cells[k] = 1;
    else lab.fill(NaN, k * 3, k * 3 + 3);
  }
  return { lab, cells, frames: grids.length };
}

/** 기준 사진 사이 간격(ms). 몇 초에 걸쳐 고르게 모아 한순간의 움직임이 몰리지 않게 한다 */
export const FRAME_GAP_MS = 200;

/** 정면을 정한 뒤 좋은 사진 frames.count장을 FRAME_GAP_MS 간격으로 모은다 */
export class BaselineCollector {
  private grids: CellLab[] = [];
  private last = -Infinity;

  /** 이 사진의 칸 색을 읽을 차례인지. 칸 색 읽기는 무거워서 먼저 묻는다 */
  wants(q: FrameQuality, center: number, now: number): boolean {
    return !this.done && now - this.last >= FRAME_GAP_MS && goodFrame(q, center);
  }

  push(grid: CellLab, now: number) {
    if (this.done) return;
    this.grids.push(grid);
    this.last = now;
  }

  get count() {
    return this.grids.length;
  }

  get done() {
    return this.grids.length >= FRAMES.count;
  }

  /** 다 모았으면 기준, 아니면 null */
  build(): Baseline | null {
    return this.done ? buildBaseline(this.grids) : null;
  }
}
