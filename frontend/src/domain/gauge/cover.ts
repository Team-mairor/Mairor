import type { Point } from "@/vision/face";
import type { CropBox } from "@/vision/occlusion";

import type { CellLab, CellSampler } from "./cells";
import { GRID } from "./spec";

/**
 * 가림 모델이 낸 가림 표(size × size, 가림이면 1)와 그 표가 놓인 정사각형.
 * 정사각형은 얼굴 점을 감싼 상자의 긴 변 × 1.4이고 사진 밖으로 나가도 된다
 */
export interface OcclusionMask {
  size: number;
  data: Uint8Array;
  box: CropBox;
}

/**
 * 사진 픽셀 (x, y)가 가림인지. 정사각형 크기로 가장 가까운 픽셀(OpenCV INTER_NEAREST: 목표 픽셀 × 줄인 비율의 내림)로
 * 되돌려 읽고, 정사각형 밖은 가림이 없다
 */
function occludedAt(mask: OcclusionMask, x: number, y: number): boolean {
  const { size, data, box } = mask;
  const mx = Math.floor(((x - box.left) * size) / box.side);
  const my = Math.floor(((y - box.top) * size) / box.side);
  if (mx < 0 || my < 0 || mx >= size || my >= size) return false;
  return data[my * size + mx] === 1;
}

/**
 * 칸마다 가린 몫(0~1)을 낸다. 칸을 읽는 표본 점(readCells와 같은 점)을 사진 자리로 옮겨,
 * 둘레 네 픽셀 중 하나라도 가리면 그 점을 가림으로 세고 칸 안 점 중 가린 점의 몫을 낸다.
 * 사진 밖으로 나가거나 점이 없는 칸은 가리지 않은 것으로 둔다
 */
export function readCover(
  mask: OcclusionMask,
  photo: { width: number; height: number },
  landmarks: Point[],
  sampler: CellSampler,
): Float32Array {
  const { width, height } = photo;
  const covered = new Uint16Array(GRID * GRID);
  const { cell, corners, weights } = sampler;
  for (let s = 0; s < cell.length; s++) {
    const a = landmarks[corners[s * 3]];
    const b = landmarks[corners[s * 3 + 1]];
    const c = landmarks[corners[s * 3 + 2]];
    if (!a || !b || !c) continue;
    const x = (a.x * weights[s * 3] + b.x * weights[s * 3 + 1] + c.x * weights[s * 3 + 2]) * width;
    const y = (a.y * weights[s * 3] + b.y * weights[s * 3 + 1] + c.y * weights[s * 3 + 2]) * height;
    if (x < 0 || y < 0 || x > width - 1 || y > height - 1) continue;
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const x1 = Math.min(x0 + 1, width - 1);
    const y1 = Math.min(y0 + 1, height - 1);
    if (
      occludedAt(mask, x0, y0) ||
      occludedAt(mask, x1, y0) ||
      occludedAt(mask, x0, y1) ||
      occludedAt(mask, x1, y1)
    )
      covered[cell[s]]++;
  }
  const out = new Float32Array(GRID * GRID);
  for (let k = 0; k < out.length; k++)
    if (sampler.samples[k]) out[k] = covered[k] / sampler.samples[k];
  return out;
}

/** 영역 가린 몫: 지금 하위 단계 영역 칸(0 · 1 표)의 칸 가린 몫 평균. 영역 칸이 없으면 0 */
export function areaCover(cellCover: Float32Array, area: Uint8Array): number {
  let sum = 0;
  let n = 0;
  for (let k = 0; k < area.length; k++)
    if (area[k]) {
      sum += cellCover[k];
      n++;
    }
  return n ? sum / n : 0;
}

/** 가린 점이 하나라도 있는 칸(칸 가린 몫 > 0)의 색을 그 장에서 비운다. 원래 표는 바꾸지 않는다 */
export function blankCovered(grid: CellLab, cellCover: Float32Array): CellLab {
  const out = Float32Array.from(grid);
  for (let k = 0; k < cellCover.length; k++) if (cellCover[k] > 0) out.fill(NaN, k * 3, k * 3 + 3);
  return out;
}
