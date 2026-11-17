import type { Baseline } from "./baseline";
import type { CellLab } from "./cells";
import { deltaE2000 } from "./color";
import { GRID, LIGHT, SKIN } from "./spec";

/** OpenCV 반올림(cvRound)처럼 .5는 짝수 쪽으로 */
const roundEven = (v: number) => {
  const r = Math.round(v);
  return Math.abs(v % 1) === 0.5 && r % 2 ? r - 1 : r;
};

/** 칸 표를 둘레 margin칸만큼 넓힌다. OpenCV 타원 구조 요소로 dilate한 것과 같다 */
export function grow(cells: Uint8Array, margin: number = LIGHT.marginCells): Uint8Array {
  if (margin <= 0) return cells;
  const offsets: [number, number][] = [];
  for (let dy = -margin; dy <= margin; dy++) {
    const dx = roundEven(margin * Math.sqrt((margin * margin - dy * dy) / (margin * margin)));
    for (let x = -dx; x <= dx; x++) offsets.push([dy, x]);
  }
  const out = new Uint8Array(cells.length);
  for (let i = 0; i < GRID; i++) {
    for (let j = 0; j < GRID; j++) {
      if (!cells[i * GRID + j]) continue;
      for (const [dy, dx] of offsets) {
        const y = i + dy;
        const x = j + dx;
        if (y >= 0 && y < GRID && x >= 0 && x < GRID) out[y * GRID + x] = 1;
      }
    }
  }
  return out;
}

/** OpenCV getGaussianKernel(ksize 0, float)과 같은 크기·값의 1차원 가우스 */
function gaussianKernel(sigma: number): Float64Array {
  const size = roundEven(sigma * 8 + 1) | 1;
  const half = (size - 1) / 2;
  const kernel = new Float64Array(size);
  let total = 0;
  for (let i = 0; i < size; i++) {
    kernel[i] = Math.exp(-((i - half) ** 2) / (2 * sigma * sigma));
    total += kernel[i];
  }
  return kernel.map((v) => v / total);
}

const KERNEL = gaussianKernel(LIGHT.sigmaCells);
const HALF = (KERNEL.length - 1) / 2;

/** 가장자리 반사(BORDER_REFLECT_101) 칸 번호. 끝 칸은 두 번 쓰지 않는다. 흐릴 때 칸마다 계산하지 않게 미리 만든다 */
const REFLECT = Int32Array.from({ length: GRID + 2 * HALF }, (_, i) => {
  let p = i - HALF;
  while (p < 0 || p >= GRID) p = p < 0 ? -p : 2 * GRID - 2 - p;
  return p;
});

/** 칸마다 네 값(쓰는 칸 · Lab 차이 셋)을 이어 붙인 표를 가로 · 세로로 한 번에 흐린다 */
function blur4(values: Float64Array): Float64Array {
  const n = KERNEL.length;
  const rows = new Float64Array(values.length);
  for (let i = 0; i < GRID; i++) {
    const row = i * GRID;
    for (let j = 0; j < GRID; j++) {
      let a = 0;
      let b = 0;
      let c = 0;
      let d = 0;
      for (let k = 0; k < n; k++) {
        const w = KERNEL[k];
        const at = (row + REFLECT[j + k]) * 4;
        a += w * values[at];
        b += w * values[at + 1];
        c += w * values[at + 2];
        d += w * values[at + 3];
      }
      const o = (row + j) * 4;
      rows[o] = a;
      rows[o + 1] = b;
      rows[o + 2] = c;
      rows[o + 3] = d;
    }
  }
  const out = new Float64Array(values.length);
  for (let i = 0; i < GRID; i++)
    for (let j = 0; j < GRID; j++) {
      let a = 0;
      let b = 0;
      let c = 0;
      let d = 0;
      for (let k = 0; k < n; k++) {
        const w = KERNEL[k];
        const at = (REFLECT[i + k] * GRID + j) * 4;
        a += w * rows[at];
        b += w * rows[at + 1];
        c += w * rows[at + 2];
        d += w * rows[at + 3];
      }
      const o = (i * GRID + j) * 4;
      out[o] = a;
      out[o + 1] = b;
      out[o + 2] = c;
      out[o + 3] = d;
    }
  return out;
}

/** 같은 바르는 칸 표는 한 번만 넓힌다 */
const grown = new WeakMap<Uint8Array, Uint8Array>();
const grownOf = (made: Uint8Array) => {
  let out = grown.get(made);
  if (!out) grown.set(made, (out = grow(made)));
  return out;
};

const hasColor = (lab: CellLab, k: number) =>
  !Number.isNaN(lab[k * 3]) && !Number.isNaN(lab[k * 3 + 1]) && !Number.isNaN(lab[k * 3 + 2]);

/** 조명을 잴 칸. 기준과 지금 모두 색이 있는 맨피부 칸에서, 바르는 칸과 그 둘레를 뺀다 */
export function freeCells(current: CellLab, base: Baseline, made: Uint8Array | null): Uint8Array {
  const margin = made ? grownOf(made) : null;
  const free = new Uint8Array(GRID * GRID);
  for (let k = 0; k < GRID * GRID; k++)
    free[k] = base.cells[k] && SKIN[k] && hasColor(current, k) && !margin?.[k] ? 1 : 0;
  return free;
}

/**
 * 칸마다 조명·카메라가 바뀐 만큼(Lab 차이). 맨피부 칸의 지금 − 기준 차이를 넓게 흐려 자리마다 낸다.
 * made는 바르는 칸이고 그 둘레 marginCells칸까지 조명 재기에서 뺀다. 잴 칸이 없으면 0이다
 */
export function lightChange(current: CellLab, base: Baseline, made: Uint8Array | null): CellLab {
  const out = new Float32Array(GRID * GRID * 3);
  const free = freeCells(current, base, made);
  if (!free.some(Boolean)) return out;
  const filled = new Float64Array(GRID * GRID * 4);
  for (let k = 0; k < GRID * GRID; k++) {
    if (!free[k]) continue;
    filled[k * 4] = 1;
    for (let ch = 0; ch < 3; ch++)
      filled[k * 4 + 1 + ch] = current[k * 3 + ch] - base.lab[k * 3 + ch];
  }
  const blurred = blur4(filled);
  for (let k = 0; k < GRID * GRID; k++) {
    const weight = Math.max(blurred[k * 4], LIGHT.minWeight);
    for (let ch = 0; ch < 3; ch++) out[k * 3 + ch] = blurred[k * 4 + 1 + ch] / weight;
  }
  return out;
}

/** 칸마다 화장이 바꾼 만큼(Lab 차이). 지금 색 − 단계 시작 기준 색 − 조명이 바뀐 만큼이다 */
export function makeupEffect(current: CellLab, base: Baseline, made: Uint8Array | null): CellLab {
  const light = lightChange(current, base, made);
  return current.map((v, i) => v - base.lab[i] - light[i]);
}

/** 화장하지 않은 피부가 맨얼굴 기준에서 바뀐 정도. 밝기·붉은 기·노란 기 차이와 ΔE2000의 가운데 값 */
export interface Drift {
  lightness: number;
  red: number;
  yellow: number;
  size: number;
  cells: number;
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(mid)] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** 카메라 자동 노출·화이트밸런스가 움직인 크기. base는 맨얼굴 기준, made는 지금까지 바른 칸이다 */
export function drift(current: CellLab, base: Baseline, made: Uint8Array | null): Drift {
  const free = freeCells(current, base, made);
  const keys = [...free.keys()].filter((k) => free[k]);
  if (!keys.length) return { lightness: NaN, red: NaN, yellow: NaN, size: NaN, cells: 0 };
  const diff = (k: number, ch: number) => current[k * 3 + ch] - base.lab[k * 3 + ch];
  return {
    lightness: median(keys.map((k) => diff(k, 0))),
    red: median(keys.map((k) => diff(k, 1))),
    yellow: median(keys.map((k) => diff(k, 2))),
    size: median(
      keys.map((k) =>
        deltaE2000(
          current[k * 3],
          current[k * 3 + 1],
          current[k * 3 + 2],
          base.lab[k * 3],
          base.lab[k * 3 + 1],
          base.lab[k * 3 + 2],
        ),
      ),
    ),
    cells: keys.length,
  };
}
