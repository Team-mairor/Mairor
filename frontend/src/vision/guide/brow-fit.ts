import type { FaceBrows, FaceFrame, MeshAnchor } from "@/vision/face";
import type { FaceMesh } from "@/vision/overlay";

import { anchorTools, browHairsAlong } from "./default-guides";
import type { GuideItem, GuideStep } from "./types";

type Pt = { x: number; y: number };
type Local = { s: number; h: number };
type Side = keyof FaceBrows;

/** 눈썹 아랫선·윗선 점 번호. 둘 다 앞머리에서 꼬리 순서다 */
const BROWS: Record<Side, { lower: number[]; upper: number[] }> = {
  rightBrow: { lower: [55, 65, 52, 53, 46], upper: [107, 66, 105, 63, 70] },
  leftBrow: { lower: [285, 295, 282, 283, 276], upper: [336, 296, 334, 293, 300] },
};
const SIDES = Object.keys(BROWS) as Side[];

/** 원래 눈썹을 찾는 칸. s는 앞머리 0 → 꼬리 1, h는 위가 +이고 둘 다 눈썹 길이 단위다 */
const FIND = { s: [-0.2, 1.2], h: [-0.6, 0.6], cols: 56, rows: 48 } as const;
/** 이보다 작게 찍힌 눈썹(px)은 찾지 않는다 */
const MIN_BROW_PX = 20;
/** 칸(세로줄) 밝기를 이 분위로 잘라 그 줄의 맨피부 밝기로 본다 */
const SKIN_PERCENTILE = 0.8;
/** 맨피부 밝기를 잴 때 점 번호 아랫선·윗선 밖으로 더 보는 범위 */
const SKIN_MARGIN = 0.3;
/** 가장 어두운 곳에서 맨피부까지 밝기 차이의 이 비율까지를 눈썹 두께로 본다 */
const HALF_DEPTH = 0.5;
/** 맨피부보다 이만큼 어두우면 눈썹. 밝기 차이와 맨피부 대비 비율 중 큰 쪽 */
const DARK_MIN = 14;
const DARK_RATIO = 0.12;
/** 점 번호 아랫선·윗선 밖으로 더 볼 범위. 눈두덩 그림자·앞머리가 들어오지 않게 좁게 둔다 */
const BELOW = 0.08;
const ABOVE = 0.12;
/** 눈썹을 찾는 앞머리(0)~꼬리(1) 범위. 앞머리 옆은 눈 안쪽 구석·콧대 그림자라 거의 넘지 않는다 */
const S_RANGE = [-0.03, 1.08] as const;
/** 한 줄 두께가 눈썹 보통 두께의 이 배를 넘으면 그 줄 가운데 쪽으로 자른다 */
const MAX_THICK_RATIO = 1.5;
/** 눈썹 보통 진하기의 이 비율보다 옅은 줄은 그림자로 보고 버린다 */
const MIN_DEPTH_RATIO = 0.5;
/** 눈썹 중심을 고를 때 가운데 값을 보는 양옆 칸 수 */
const CENTER_COLUMNS = 3;
/** 눈썹 중심을 고르는 점 번호 아랫선·윗선 밖 범위 */
const CORE_MARGIN = 0.03;
/** 이웃 칸에서 이어지는 눈썹으로 볼 가운데 높이 차이(칸). 더 떨어진 어두운 곳은 머리카락·그림자로 본다 */
const MAX_JUMP = 3;
/** 한 칸에서 이보다 두꺼운(눈썹 길이 단위) 어두운 줄은 그림자와 붙은 것으로 보고 버린다 */
const MAX_THICKNESS = 0.45;
/** 테두리를 고를 때 양옆으로 보는 칸 수 */
const SMOOTH_COLUMNS = 2;
/** 앞머리~꼬리 칸 중 이만큼은 눈썹이 있어야 찾은 것으로 본다 */
const MIN_COVERAGE = 0.6;
const MIN_CELLS = 30;
/** 평균 두께가 이보다 얇으면 그림자·선으로 보고 버린다 */
const MIN_THICKNESS = 0.05;

/** 원래 눈썹 윗선·아랫선을 다듬는 곡선 차수와 다시 뽑는 점 수 */
const CURVE_DEGREE = 3;
const CURVE_SAMPLES = 24;
/** 찾은 눈썹 길이가 랜드마크 눈썹 길이의 이 범위를 벗어나면 잘못 찾은 것으로 보고 맞추지 않는다 */
const LENGTH_RANGE = [0.6, 1.4] as const;
/** 앞머리·꼬리가 랜드마크에서 이만큼(눈썹 길이 단위)보다 멀면 맞추지 않는다 */
const MAX_END_SHIFT = 0.35;

interface Axis {
  o: Pt;
  u: Pt;
  n: Pt;
  len: number;
}

export function axisOf(head: Pt, tail: Pt): Axis {
  const dx = tail.x - head.x;
  const dy = tail.y - head.y;
  const len = Math.hypot(dx, dy) || 1;
  const u = { x: dx / len, y: dy / len };
  // 화면·얼굴 지도 모두 아래가 +y라 y가 줄어드는 쪽을 위로 둔다
  const n = u.x >= 0 ? { x: u.y, y: -u.x } : { x: -u.y, y: u.x };
  return { o: head, u, n, len };
}

export function toLocal(a: Axis, p: Pt): Local {
  const x = p.x - a.o.x;
  const y = p.y - a.o.y;
  return { s: (x * a.u.x + y * a.u.y) / a.len, h: (x * a.n.x + y * a.n.y) / a.len };
}

export function fromLocal(a: Axis, s: number, h: number): Pt {
  return {
    x: a.o.x + a.len * (s * a.u.x + h * a.n.x),
    y: a.o.y + a.len * (s * a.u.y + h * a.n.y),
  };
}

/** s 순서로 이은 점 번호 선의 높이. 양 끝 밖은 끝 높이를 쓴다 */
function curveAt(points: Local[], s: number) {
  if (s <= points[0].s) return points[0].h;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    if (s <= b.s) return a.h + ((b.h - a.h) * (s - a.s)) / (b.s - a.s || 1);
  }
  return points[points.length - 1].h;
}

function cellGrid(grid: {
  s: readonly number[];
  h: readonly number[];
  cols: number;
  rows: number;
}) {
  const ds = (grid.s[1] - grid.s[0]) / grid.cols;
  const dh = (grid.h[1] - grid.h[0]) / grid.rows;
  return {
    ds,
    dh,
    sAt: (c: number) => grid.s[0] + (c + 0.5) * ds,
    hAt: (r: number) => grid.h[0] + (r + 0.5) * dh,
  };
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
};

/** 등록 사진의 RGBA 픽셀 */
export interface Pixels {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

/** p(px) 둘레 (2r+1)² 픽셀의 평균 밝기. 사진 밖이면 NaN */
function brightness(image: Pixels, p: Pt, r: number) {
  const cx = Math.round(p.x);
  const cy = Math.round(p.y);
  if (cx - r < 0 || cy - r < 0 || cx + r >= image.width || cy + r >= image.height) return NaN;
  let sum = 0;
  for (let y = cy - r; y <= cy + r; y++) {
    for (let x = cx - r; x <= cx + r; x++) {
      const i = (y * image.width + x) * 4;
      sum += 0.299 * image.data[i] + 0.587 * image.data[i + 1] + 0.114 * image.data[i + 2];
    }
  }
  return sum / (2 * r + 1) ** 2;
}

/** 원래 눈썹 테두리(px). 맨피부보다 어두운 칸 덩어리의 칸별 아래·위 끝을 잇는다. 못 찾으면 null */
function findBrow(image: Pixels, px: Pt[], brow: (typeof BROWS)[Side]): Pt[] | null {
  const axis = axisOf(px[brow.lower[0]], px[brow.lower[brow.lower.length - 1]]);
  if (axis.len < MIN_BROW_PX) return null;
  const bySide = (a: Local, b: Local) => a.s - b.s;
  const lower = brow.lower.map((i) => toLocal(axis, px[i])).sort(bySide);
  const upper = brow.upper.map((i) => toLocal(axis, px[i])).sort(bySide);
  const { cols, rows } = FIND;
  const { ds, dh, sAt, hAt } = cellGrid(FIND);
  const r = Math.max(0, Math.floor((axis.len * ds) / 2));

  const values = new Float32Array(cols * rows);
  for (let row = 0; row < rows; row++)
    for (let c = 0; c < cols; c++)
      values[row * cols + c] = brightness(image, fromLocal(axis, sAt(c), hAt(row)), r);
  // 점 번호 눈썹 둘레만 본다. 앞머리·눈두덩은 여기서 대부분 빠진다
  const allowed = (c: number, row: number) => {
    const sv = sAt(c);
    const h = hAt(row);
    return (
      sv >= S_RANGE[0] &&
      sv <= S_RANGE[1] &&
      h >= curveAt(lower, sv) - BELOW &&
      h <= curveAt(upper, sv) + ABOVE &&
      Number.isFinite(values[row * cols + c])
    );
  };
  // 눈썹 가운데에서 시작해 양옆으로, 칸(세로줄)마다 이웃 칸과 이어지는 가장 어두운 곳을 눈썹 중심으로 잡는다.
  // 두께는 그 칸 맨피부와의 밝기 차이가 절반이 되는 곳까지라, 서서히 어두워지는 눈두덩 그림자는 빠진다
  const maxRows = MAX_THICKNESS / dh;
  const low = new Array<number>(cols).fill(NaN);
  const high = new Array<number>(cols).fill(NaN);
  const at = (c: number, row: number) => values[row * cols + c];
  const skinOf = (c: number) => {
    const sv = sAt(c);
    const column: number[] = [];
    for (let row = 0; row < rows; row++) {
      const h = hAt(row);
      if (h >= curveAt(lower, sv) - SKIN_MARGIN && h <= curveAt(upper, sv) + SKIN_MARGIN) {
        if (Number.isFinite(at(c, row))) column.push(at(c, row));
      }
    }
    return column.length
      ? [...column].sort((a, b) => a - b)[Math.floor(column.length * SKIN_PERCENTILE)]
      : NaN;
  };
  // 중심은 점 번호 눈썹 안에서만 고른다. 위로 내려온 앞머리 가닥이 더 어두워도 중심이 되지 않게 한다
  const core = (c: number, row: number) => {
    const sv = sAt(c);
    const h = hAt(row);
    return (
      allowed(c, row) &&
      h >= curveAt(lower, sv) - CORE_MARGIN &&
      h <= curveAt(upper, sv) + CORE_MARGIN
    );
  };
  // 1) 칸마다 이웃 칸과 이어지는 가장 어두운 곳을 중심 후보로 잡는다
  const darkestRow = (c: number, center: number | null) => {
    let best = -1;
    for (let row = 0; row < rows; row++) {
      if (!core(c, row)) continue;
      if (center !== null && Math.abs(row - center) > MAX_JUMP) continue;
      if (best < 0 || at(c, row) < at(c, best)) best = row;
    }
    return best < 0 ? null : best;
  };
  const centers = new Array<number>(cols).fill(NaN);
  const start = [...Array(cols).keys()].reduce((a, b) =>
    Math.abs(sAt(a) - 0.5) <= Math.abs(sAt(b) - 0.5) ? a : b,
  );
  const first = darkestRow(start, null);
  if (first === null) return null;
  centers[start] = first;
  for (const step of [1, -1]) {
    let center = first;
    for (let c = start + step; c >= 0 && c < cols; c += step) {
      const row = darkestRow(c, center);
      if (row === null) continue;
      centers[c] = row;
      center = row;
    }
  }
  // 2) 이웃 칸의 가운데 값으로 중심을 고른다. 몇 칸에 걸친 앞머리 가닥에 중심이 끌려가지 않는다
  const picked = [...Array(cols).keys()].filter((c) => Number.isFinite(centers[c]));
  // 3) 중심에서 맨피부와의 밝기 차이가 절반이 되는 곳까지 넓힌다
  const depths = new Array<number>(cols).fill(NaN);
  const middles = new Array<number>(cols).fill(NaN);
  picked.forEach((c, k) => {
    const near = picked.slice(Math.max(0, k - CENTER_COLUMNS), k + CENTER_COLUMNS + 1);
    const row = Math.round(median(near.map((n) => centers[n])));
    if (!allowed(c, row)) return;
    const darkest = at(c, row);
    const skin = skinOf(c);
    const depth = skin - darkest;
    if (!(depth >= Math.max(DARK_MIN, DARK_RATIO * skin))) return;
    const edge = darkest + depth * HALF_DEPTH;
    // 눈썹보다 훨씬 어두운 곳(머리카락·속눈썹)이 붙어 있으면 거기서 멈춘다
    const grows = (r: number) => allowed(c, r) && at(c, r) < edge && at(c, r) >= darkest - DARK_MIN;
    let from = row;
    let to = row;
    while (from > 0 && grows(from - 1)) from--;
    while (to < rows - 1 && grows(to + 1)) to++;
    if (to - from + 1 > maxRows) return;
    low[c] = from;
    high[c] = to;
    depths[c] = depth;
    middles[c] = row;
  });
  // 4) 눈썹 보통 진하기·두께에서 크게 벗어난 줄을 고친다. 앞머리 옆 그림자로 테두리가 꺾여 내려가지 않게 한다
  const grown = [...Array(cols).keys()].filter((c) => Number.isFinite(low[c]));
  if (grown.length) {
    const usualDepth = median(grown.map((c) => depths[c]));
    const usualThickness = median(grown.map((c) => high[c] - low[c] + 1));
    const half = (usualThickness * MAX_THICK_RATIO) / 2;
    for (const c of grown) {
      if (depths[c] < usualDepth * MIN_DEPTH_RATIO) {
        low[c] = NaN;
        high[c] = NaN;
        continue;
      }
      if (high[c] - low[c] + 1 > usualThickness * MAX_THICK_RATIO) {
        low[c] = Math.max(low[c], Math.round(middles[c] - half));
        high[c] = Math.min(high[c], Math.round(middles[c] + half));
      }
    }
  }
  const found = [...Array(cols).keys()].filter((c) => Number.isFinite(low[c]));
  const cells = found.reduce((sum, c) => sum + high[c] - low[c] + 1, 0);
  if (cells < MIN_CELLS) return null;
  const span = [...Array(cols).keys()].filter((c) => sAt(c) >= 0.1 && sAt(c) <= 0.9);
  if (span.filter((c) => Number.isFinite(low[c])).length < span.length * MIN_COVERAGE) return null;

  // 이웃 칸의 가운데 값으로 들쭉날쭉한 테두리를 고른다
  const smooth = (edge: number[], k: number) =>
    median(
      found.slice(Math.max(0, k - SMOOTH_COLUMNS), k + SMOOTH_COLUMNS + 1).map((c) => edge[c]),
    );
  const edges = found.map((c, k) => ({
    s: sAt(c),
    low: hAt(smooth(low, k)) - dh / 2,
    high: hAt(smooth(high, k)) + dh / 2,
  }));
  const thickness = edges.reduce((sum, e) => sum + e.high - e.low, 0) / edges.length;
  if (thickness < MIN_THICKNESS) return null;
  return [
    ...edges.map((e) => fromLocal(axis, e.s, e.low)),
    ...[...edges].reverse().map((e) => fromLocal(axis, e.s, e.high)),
  ];
}

/** 점 p를 points 위 메시 삼각형 기준점으로 바꾼다. 삼각형 밖이면 가장 가까운 삼각형 */
function anchorOn(points: Pt[], mesh: FaceMesh, p: Pt): MeshAnchor {
  let best: MeshAnchor = { triangle: 0, bary: [1, 0, 0] };
  let score = Infinity;
  mesh.triangles.forEach(([ia, ib, ic], triangle) => {
    const a = points[ia];
    const b = points[ib];
    const c = points[ic];
    const det = (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y);
    if (Math.abs(det) < 1e-10) return;
    const v = ((p.x - a.x) * (c.y - a.y) - (c.x - a.x) * (p.y - a.y)) / det;
    const w = ((b.x - a.x) * (p.y - a.y) - (p.x - a.x) * (b.y - a.y)) / det;
    const outside = -Math.min(1 - v - w, v, w);
    if (outside < score) {
      score = outside;
      best = { triangle, bary: [1 - v - w, v, w] };
    }
  });
  return best;
}

/** 등록 사진에서 원래 눈썹을 찾아 메시 기준점으로 바꾼다. 못 찾은 쪽은 비운다 */
export function findBrows(image: Pixels, frame: FaceFrame, mesh: FaceMesh): FaceBrows {
  const px = frame.landmarks.map((p) => ({ x: p.x * image.width, y: p.y * image.height }));
  const brows: FaceBrows = {};
  for (const side of SIDES) {
    const outline = findBrow(image, px, BROWS[side]);
    if (outline) brows[side] = outline.map((p) => anchorOn(px, mesh, p));
  }
  return brows;
}

interface BrowSpan {
  axis: Axis;
  /** 원래 눈썹 앞머리·꼬리. 꼬리는 랜드마크 꼬리보다 짧게 찾혀도 랜드마크 꼬리(1)까지 본다 */
  head: number;
  tail: number;
  /** 찾은 원래 눈썹의 아랫선·윗선 (앞머리 → 꼬리) */
  low: Local[];
  high: Local[];
  /** 랜드마크 눈썹 아랫선·윗선. 찾은 범위 밖은 이 모양으로 잇는다 */
  landmarkLow: Local[];
  landmarkHigh: Local[];
}

/**
 * 쪽마다 원래 눈썹의 앞머리·꼬리 자리와 윗선·아랫선. 랜드마크 눈썹 앞머리를 0, 꼬리를 1로 둔 눈썹 길이 단위다.
 * 꼬리는 끝으로 갈수록 옅어 찍을 때마다 짧게 잡히므로, 랜드마크 꼬리보다 길게 찾았을 때만 늘린다.
 * 원래 눈썹이 없거나 찾은 길이·자리가 이상한 쪽은 뺀다
 */
export function browSpans(brows: FaceBrows, mesh: FaceMesh): Partial<Record<Side, BrowSpan>> {
  const uvPt = (i: number): Pt => ({ x: mesh.uv[i][0], y: mesh.uv[i][1] });
  const spans: Partial<Record<Side, BrowSpan>> = {};
  for (const side of SIDES) {
    const own = brows[side];
    if (!own || own.length < 4) continue;
    const { lower, upper } = BROWS[side];
    const axis = axisOf(uvPt(lower[0]), uvPt(lower[lower.length - 1]));
    const local = own.map((a) => toLocal(axis, uvOfAnchor(a, mesh)));
    const along = local.map((p) => p.s);
    const head = Math.min(...along);
    const found = Math.max(...along);
    if (found - head < LENGTH_RANGE[0] || found - head > LENGTH_RANGE[1]) continue;
    if (Math.abs(head) > MAX_END_SHIFT || Math.abs(found - 1) > MAX_END_SHIFT) continue;
    // 테두리는 아랫선(앞머리 → 꼬리) 뒤에 윗선(꼬리 → 앞머리)을 이은 것이다
    const half = Math.floor(local.length / 2);
    const bySide = (a: Local, b: Local) => a.s - b.s;
    // 털 하나하나의 삐죽함은 따라가지 않도록 윗선·아랫선을 매끄러운 곡선으로 다듬는다
    const low = smoothCurve(local.slice(0, half));
    const high = smoothCurve(local.slice(half)).map((p, k) => ({
      s: p.s,
      h: Math.max(p.h, (low[k]?.h ?? p.h) + MIN_THICKNESS),
    }));
    spans[side] = {
      axis,
      head,
      tail: Math.max(1, found),
      low,
      high,
      landmarkLow: lower.map((i) => toLocal(axis, uvPt(i))).sort(bySide),
      landmarkHigh: upper.map((i) => toLocal(axis, uvPt(i))).sort(bySide),
    };
  }
  return spans;
}

/** 점들에 맞춘 다항식 계수(낮은 차수부터). 최소제곱 */
function polyFit(points: Local[], degree: number) {
  const n = degree + 1;
  const a = Array.from({ length: n }, () => new Array<number>(n + 1).fill(0));
  for (const { s, h } of points)
    for (let r = 0; r < n; r++) {
      for (let c = 0; c < n; c++) a[r][c] += s ** (r + c);
      a[r][n] += h * s ** r;
    }
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let r = col + 1; r < n; r++) if (Math.abs(a[r][col]) > Math.abs(a[pivot][col])) pivot = r;
    [a[col], a[pivot]] = [a[pivot], a[col]];
    if (Math.abs(a[col][col]) < 1e-12) return null;
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = a[r][col] / a[col][col];
      for (let c = col; c <= n; c++) a[r][c] -= f * a[col][c];
    }
  }
  return a.map((row, r) => row[n] / row[r]);
}

/** 찾은 선을 3차 곡선으로 맞춰 고르게 다시 뽑는다. 점이 적으면 차수를 낮춘다 */
function smoothCurve(points: Local[]): Local[] {
  const sorted = [...points].sort((a, b) => a.s - b.s);
  const degree = Math.min(CURVE_DEGREE, sorted.length - 2);
  const coef = degree >= 1 ? polyFit(sorted, degree) : null;
  if (!coef) return sorted;
  const first = sorted[0].s;
  const last = sorted[sorted.length - 1].s;
  return Array.from({ length: CURVE_SAMPLES }, (_, k) => {
    const sv = first + ((last - first) * k) / (CURVE_SAMPLES - 1);
    return { s: sv, h: coef.reduce((sum, c, i) => sum + c * sv ** i, 0) };
  });
}

/** 찾은 선의 높이. 찾은 범위 밖은 랜드마크 선 모양을 끝 높이에 이어 붙인다 */
function edgeAt(found: Local[], landmark: Local[], s: number) {
  const first = found[0];
  const last = found[found.length - 1];
  if (s < first.s) return curveAt(landmark, s) + first.h - curveAt(landmark, first.s);
  if (s > last.s) return curveAt(landmark, s) + last.h - curveAt(landmark, last.s);
  return curveAt(found, s);
}

const isBrowStep = (step: GuideStep) =>
  step.regions.length > 0 &&
  step.regions.every((region) => region === "rightBrow" || region === "leftBrow");

const anchorsOf = (guide: GuideItem): MeshAnchor[] =>
  guide.type === "point"
    ? [guide.at]
    : guide.type === "arrow"
      ? [guide.from, guide.to]
      : guide.type === "polyline"
        ? guide.path
        : guide.outline;

/** 도형이 어느 쪽 눈썹인지. 얼굴 지도에서 x가 0.5보다 작은 쪽이 본인 기준 오른쪽이다 */
function sideOf(guide: GuideItem, mesh: FaceMesh): Side {
  if (guide.region === "rightBrow" || guide.region === "leftBrow") return guide.region;
  const points = anchorsOf(guide).map((a) => uvOfAnchor(a, mesh));
  return points.reduce((sum, p) => sum + p.x, 0) / points.length < 0.5 ? "rightBrow" : "leftBrow";
}

function uvOfAnchor({ triangle, bary }: MeshAnchor, mesh: FaceMesh): Pt {
  const [a, b, c] = mesh.triangles[triangle].map((i) => mesh.uv[i]);
  return {
    x: a[0] * bary[0] + b[0] * bary[1] + c[0] * bary[2],
    y: a[1] * bary[0] + b[1] * bary[1] + c[1] * bary[2],
  };
}

/**
 * 눈썹 단계 가이드를 그대로 두고 앞머리·꼬리 위치만 등록 사진의 원래 눈썹에 맞춘다.
 * 가이드를 랜드마크 눈썹(앞머리 0 → 꼬리 1) 기준으로 원래 눈썹의 앞머리~꼬리에 늘이거나 줄이고, 높이는 바꾸지 않는다.
 * 원래 눈썹을 못 찾았거나 찾은 길이가 이상한 쪽, 눈썹 단계가 아닌 단계는 그대로 둔다
 */
export function alignBrowStep(step: GuideStep, brows: FaceBrows | null, mesh: FaceMesh): GuideStep {
  if (!brows || !isBrowStep(step)) return step;
  const spans = browSpans(brows, mesh);
  if (!Object.keys(spans).length) return step;
  const { anchorAt } = anchorTools(mesh);
  const guides = step.guides.map((guide): GuideItem => {
    const fit = spans[sideOf(guide, mesh)];
    if (!fit) return guide;
    const move = (a: MeshAnchor) => {
      const { s, h } = toLocal(fit.axis, uvOfAnchor(a, mesh));
      return anchorAt(fromLocal(fit.axis, fit.head + s * (fit.tail - fit.head), h));
    };
    switch (guide.type) {
      case "point":
        return { ...guide, at: move(guide.at) };
      case "arrow":
        return { ...guide, from: move(guide.from), to: move(guide.to) };
      case "polyline":
        return { ...guide, path: guide.path.map(move) };
      case "polygon":
        return { ...guide, outline: guide.outline.map(move) };
    }
  });
  return { ...step, guides };
}

/**
 * 눈썹 단계를 원래 눈썹에 맞춘다. 기본 가이드의 결은 같은 결을 원래 눈썹 윗선·아랫선을 따라 다시 그려 모양을 맞추고,
 * 영상에서 찾은 영역처럼 결이 아닌 도형은 목표 모양을 지키도록 앞머리·꼬리만 맞춘다(alignBrowStep).
 * 원래 눈썹을 못 찾은 쪽과 눈썹 단계가 아닌 단계는 그대로 둔다
 */
export function fitBrowStep(step: GuideStep, brows: FaceBrows | null, mesh: FaceMesh): GuideStep {
  if (!brows || !isBrowStep(step)) return step;
  const spans = browSpans(brows, mesh);
  if (!Object.keys(spans).length) return step;
  const isHair = (g: GuideItem) => g.type === "polyline" && !!g.brush;
  const others = step.guides.filter((g) => !isHair(g));
  const aligned = others.length
    ? alignBrowStep({ ...step, guides: others }, brows, mesh).guides
    : [];
  const { anchorAt } = anchorTools(mesh);
  const hairsOf = (side: Side): GuideItem[] => {
    const span = spans[side]!;
    return browHairsAlong((sv, f) => {
      const s = span.head + sv * (span.tail - span.head);
      const low = edgeAt(span.low, span.landmarkLow, s);
      const high = edgeAt(span.high, span.landmarkHigh, s);
      return anchorAt(fromLocal(span.axis, s, low + (high - low) * f));
    }).map((g): GuideItem => ({ ...g, region: side }));
  };
  // 그리는 순서는 그대로 두고, 다시 그린 결은 그쪽 첫 결 자리에 넣는다
  let next = 0;
  const placed = new Set<Side>();
  const guides = step.guides.flatMap((guide): GuideItem[] => {
    if (!isHair(guide)) return [aligned[next++]];
    const side = sideOf(guide, mesh);
    if (!spans[side]) return [guide];
    if (placed.has(side)) return [];
    placed.add(side);
    return hairsOf(side);
  });
  return { ...step, guides };
}
