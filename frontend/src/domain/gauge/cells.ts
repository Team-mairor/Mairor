import type { Point } from "@/vision/face";
import type { FaceMesh } from "@/vision/overlay";

import { rgbToLab } from "./color";
import { GRID, MEASURED, SHARE_MIN } from "./spec";

/** 카메라 프레임의 RGBA 픽셀 */
export interface Pixels {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

/** 칸마다 Lab 세 값(칸 번호 × 3). 색을 못 낸 칸은 NaN이다 */
export type CellLab = Float32Array;

/** 한 칸을 SUB × SUB 점으로 읽는다. AI는 칸마다 8 × 8 지도 픽셀을 평균한다 */
const SUB = 4;
const SIDE = GRID * SUB;

/** 칸 안 표본 점마다 속한 얼굴 메시 삼각형의 세 꼭짓점과 비율. 얼굴 지도는 고정이라 한 번만 만든다 */
export interface CellSampler {
  cell: Int32Array;
  corners: Int32Array;
  weights: Float32Array;
  /** 칸마다 표본 점 수 */
  samples: Uint16Array;
}

export function cellSampler(mesh: FaceMesh): CellSampler {
  const owner = new Int32Array(SIDE * SIDE).fill(-1);
  const bary = new Float32Array(SIDE * SIDE * 3);
  mesh.triangles.forEach(([ia, ib, ic], t) => {
    const [ax, ay] = mesh.uv[ia];
    const [bx, by] = mesh.uv[ib];
    const [cx, cy] = mesh.uv[ic];
    const area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
    if (Math.abs(area) < 1e-12) return;
    const at = (v: number) => v * SIDE - 0.5;
    const x0 = Math.max(0, Math.ceil(at(Math.min(ax, bx, cx))));
    const x1 = Math.min(SIDE - 1, Math.floor(at(Math.max(ax, bx, cx))));
    const y0 = Math.max(0, Math.ceil(at(Math.min(ay, by, cy))));
    const y1 = Math.min(SIDE - 1, Math.floor(at(Math.max(ay, by, cy))));
    for (let y = y0; y <= y1; y++) {
      const py = (y + 0.5) / SIDE;
      for (let x = x0; x <= x1; x++) {
        const k = y * SIDE + x;
        if (owner[k] >= 0) continue;
        const px = (x + 0.5) / SIDE;
        const wb = ((px - ax) * (cy - ay) - (cx - ax) * (py - ay)) / area;
        const wc = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area;
        const wa = 1 - wb - wc;
        if (wa < -1e-9 || wb < -1e-9 || wc < -1e-9) continue;
        owner[k] = t;
        bary.set([wa, wb, wc], k * 3);
      }
    }
  });

  const cell: number[] = [];
  const corners: number[] = [];
  const weights: number[] = [];
  const samples = new Uint16Array(GRID * GRID);
  for (let k = 0; k < SIDE * SIDE; k++) {
    const t = owner[k];
    if (t < 0) continue;
    const c = Math.floor(k / SIDE / SUB) * GRID + Math.floor((k % SIDE) / SUB);
    if (!MEASURED[c]) continue;
    cell.push(c);
    corners.push(...mesh.triangles[t]);
    weights.push(bary[k * 3], bary[k * 3 + 1], bary[k * 3 + 2]);
    samples[c]++;
  }
  return {
    cell: Int32Array.from(cell),
    corners: Int32Array.from(corners),
    weights: Float32Array.from(weights),
    samples,
  };
}

/**
 * 프레임을 얼굴 지도로 펴 칸마다 평균 색을 Lab으로 낸다.
 * 표본 점은 사진에서 같은 삼각형의 같은 비율 자리를 둘레 네 픽셀로 섞어 읽는다(AI flatten과 같은 방식).
 * 재는 칸이 아니거나 표본이 SHARE_MIN만큼 읽히지 않은 칸은 NaN이다
 */
export function readCells(pixels: Pixels, landmarks: Point[], sampler: CellSampler): CellLab {
  const { width, height, data } = pixels;
  const sum = new Float64Array(GRID * GRID * 3);
  const count = new Uint16Array(GRID * GRID);
  const { cell, corners, weights } = sampler;
  for (let s = 0; s < cell.length; s++) {
    const a = landmarks[corners[s * 3]];
    const b = landmarks[corners[s * 3 + 1]];
    const c = landmarks[corners[s * 3 + 2]];
    if (!a || !b || !c) continue;
    const wa = weights[s * 3];
    const wb = weights[s * 3 + 1];
    const wc = weights[s * 3 + 2];
    const x = (a.x * wa + b.x * wb + c.x * wc) * width;
    const y = (a.y * wa + b.y * wb + c.y * wc) * height;
    if (x < 0 || y < 0 || x > width - 1 || y > height - 1) continue;
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const x1 = Math.min(x0 + 1, width - 1);
    const y1 = Math.min(y0 + 1, height - 1);
    const right = x - x0;
    const down = y - y0;
    const i00 = (y0 * width + x0) * 4;
    const i01 = (y0 * width + x1) * 4;
    const i10 = (y1 * width + x0) * 4;
    const i11 = (y1 * width + x1) * 4;
    const k = cell[s];
    for (let ch = 0; ch < 3; ch++) {
      const top = data[i00 + ch] * (1 - right) + data[i01 + ch] * right;
      const bottom = data[i10 + ch] * (1 - right) + data[i11 + ch] * right;
      sum[k * 3 + ch] += Math.round(top * (1 - down) + bottom * down);
    }
    count[k]++;
  }
  const out = new Float32Array(GRID * GRID * 3).fill(NaN);
  for (let k = 0; k < GRID * GRID; k++) {
    const total = sampler.samples[k];
    if (!total || count[k] < total * SHARE_MIN) continue;
    const n = count[k];
    out.set(rgbToLab(sum[k * 3] / n, sum[k * 3 + 1] / n, sum[k * 3 + 2] / n), k * 3);
  }
  return out;
}
