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

/** 가장자리 반사(BORDER_REFLECT_101). 끝 칸은 두 번 쓰지 않는다 */
const reflect = (p: number, n: number) => {
  let i = p;
  while (i < 0 || i >= n) i = i < 0 ? -i : 2 * n - 2 - i;
  return i;
};

/** GRID × GRID 표 하나를 가로·세로로 흐린다 */
function blur(values: Float64Array, kernel: Float64Array): Float64Array {
  const half = (kernel.length - 1) / 2;
  const rows = new Float64Array(values.length);
  for (let i = 0; i < GRID; i++)
    for (let j = 0; j < GRID; j++) {
      let s = 0;
      for (let k = 0; k < kernel.length; k++)
        s += kernel[k] * values[i * GRID + reflect(j + k - half, GRID)];
      rows[i * GRID + j] = s;
    }
  const out = new Float64Array(values.length);
  for (let i = 0; i < GRID; i++)
    for (let j = 0; j < GRID; j++) {
      let s = 0;
      for (let k = 0; k < kernel.length; k++)
        s += kernel[k] * rows[reflect(i + k - half, GRID) * GRID + j];
      out[i * GRID + j] = s;
    }
  return out;
}

const hasColor = (lab: CellLab, k: number) =>
  !Number.isNaN(lab[k * 3]) && !Number.isNaN(lab[k * 3 + 1]) && !Number.isNaN(lab[k * 3 + 2]);

/** 조명을 잴 칸. 기준과 지금 모두 색이 있는 맨피부 칸에서, 바르는 칸과 그 둘레를 뺀다 */
export function freeCells(current: CellLab, base: Baseline, made: Uint8Array | null): Uint8Array {
  const grown = made ? grow(made) : null;
  const free = new Uint8Array(GRID * GRID);
  for (let k = 0; k < GRID * GRID; k++)
    free[k] = base.cells[k] && SKIN[k] && hasColor(current, k) && !grown?.[k] ? 1 : 0;
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
  const kernel = gaussianKernel(LIGHT.sigmaCells);
  const count = blur(Float64Array.from(free), kernel);
  for (let ch = 0; ch < 3; ch++) {
    const filled = new Float64Array(GRID * GRID);
    for (let k = 0; k < GRID * GRID; k++)
      if (free[k]) filled[k] = current[k * 3 + ch] - base.lab[k * 3 + ch];
    const total = blur(filled, kernel);
    for (let k = 0; k < GRID * GRID; k++)
      out[k * 3 + ch] = total[k] / Math.max(count[k], LIGHT.minWeight);
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
