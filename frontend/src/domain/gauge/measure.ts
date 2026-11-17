// 사용자 캠 화장의 진하기와 색감을 레퍼런스와 같은 눈금으로 잰다. AI tools/gauge/measure.py와 같은 식이다.
// 값은 AI(Python)와 같이 쓰도록 shared/gauge/measure.v1.json에 둔다.

import type { GaugeReference } from "@/vision/guide";

import type { Baseline } from "./baseline";
import type { CellLab } from "./cells";
import { deltaE2000 } from "./color";
import { lightChange } from "./light";
import { GRID } from "./spec";
import raw from "../../../../shared/gauge/measure.v1.json" with { type: "json" };

export type Vec3 = [number, number, number];
export type MeasureReason = "noReference" | "noWhite" | "tooFewCells" | "thinArea";
export type Combine = "weaker" | "stronger" | "mean";

export type MatchMethod =
  | {
      name: "mix";
      anchor: "skin" | "white";
      degree: "full" | "chroma";
      weight: number;
    }
  | { name: "local"; target: "reference" | "user" | "average"; space: "rgb" };

/** 잴 칸이 이보다 적으면 tooFewCells */
export const MIN_AREA_CELLS: number = raw.area.minCells;
/** 재지 않는 화장 종류(thinArea) */
export const THIN_MAKEUPS: readonly string[] = raw.area.thinMakeups;
/** 흰자를 기준으로 레퍼런스와 사용자 화면의 색·밝기를 맞추는 방법 */
export const COLOR_METHOD: MatchMethod = {
  name: "mix",
  anchor: raw.methods.color.anchor as "white",
  degree: ("degree" in raw.methods.color ? raw.methods.color.degree : "full") as "full" | "chroma",
  weight: raw.methods.color.weight,
};
export const DARK_METHOD: MatchMethod = {
  name: "local",
  target: raw.methods.dark.target as "user",
  space: raw.methods.dark.space as "rgb",
};
/** 자리마다 비율로 맞추고 색감은 내지 않는 화장 종류 */
export const DARK_MAKEUPS: readonly string[] = raw.methods.darkMakeups;
const LEAST_PAINT_MIN: number = raw.methods.leastPaintMin;
export const COMBINE = raw.combine as Combine;
export const BAR: { atReference: number; max: number } = raw.bar;
const COLOR = raw.color;
/** 칸 색을 재는 간격과 가운데 값으로 모으는 최근 시간(ms) */
export const MEASURE_FRAMES: { intervalMs: number; medianWindowMs: number } = raw.frames;
const TINY = 1e-6;

const LUMA: Vec3 = [0.212671, 0.71516, 0.072169];
const SRGB_TO_XYZ = [[0.412453, 0.35758, 0.180423], LUMA, [0.019334, 0.119193, 0.950227]];
const D65 = [0.950456, 1, 1.088754];
const EPS = 6 / 29;

function inverse3(m: number[][]): number[][] {
  const [[a, b, c], [d, e, f], [g, h, i]] = m;
  const A = e * i - f * h;
  const B = -(d * i - f * g);
  const C = d * h - e * g;
  const det = a * A + b * B + c * C;
  return [
    [A / det, -(b * i - c * h) / det, (b * f - c * e) / det],
    [B / det, (a * i - c * g) / det, -(a * f - c * d) / det],
    [C / det, -(a * h - b * g) / det, (a * e - b * d) / det],
  ];
}
const XYZ_TO_SRGB = inverse3(SRGB_TO_XYZ);

const apply = (m: number[][], v: Vec3): Vec3 =>
  m.map((row) => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]) as Vec3;
const map3 = (v: Vec3, fn: (x: number, i: number) => number): Vec3 =>
  [fn(v[0], 0), fn(v[1], 1), fn(v[2], 2)] as Vec3;
const sub = (a: Vec3, b: Vec3) => map3(a, (x, i) => x - b[i]);
const dot = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a: Vec3) => Math.sqrt(dot(a, a));
const clip0 = (v: Vec3) => map3(v, (x) => Math.max(x, 0));
const de = (a: Vec3, b: Vec3) => deltaE2000(a[0], a[1], a[2], b[0], b[1], b[2]);

/** 선형 RGB(0~1)를 Lab(D65)으로 */
export function labOf(linear: Vec3): Vec3 {
  const xyz = map3(apply(SRGB_TO_XYZ, linear), (x, i) => x / D65[i]);
  const f = map3(xyz, (t) => (t > EPS ** 3 ? Math.cbrt(t) : t / (3 * EPS ** 2) + 4 / 29));
  return [116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])];
}

/** Lab(D65)을 선형 RGB로. 범위를 넘는 값은 자르지 않는다 */
export function linearOfLab(lab: Vec3): Vec3 {
  const fy = (lab[0] + 16) / 116;
  const f: Vec3 = [fy + lab[1] / 500, fy, fy - lab[2] / 200];
  const xyz = map3(f, (t, i) => (t > EPS ? t ** 3 : 3 * EPS ** 2 * (t - 4 / 29)) * D65[i]);
  return apply(XYZ_TO_SRGB, xyz);
}

/** 0~255 sRGB(소수 가능)를 선형 RGB로 */
export function linearOfSrgb(rgb: Vec3): Vec3 {
  return map3(rgb, (v) => {
    const c = v / 255;
    return c > 0.04045 ? ((c + 0.055) / 1.055) ** 2.4 : c / 12.92;
  });
}

/** #RRGGBB를 선형 RGB로 */
export const linearOfHex = (hex: string): Vec3 =>
  linearOfSrgb([1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Vec3);

/** 한 화면에서 잰 영역. 색은 모두 선형 RGB(0~1)다. white는 흰자 색이고 없으면 null */
export interface AreaSide {
  before: Vec3;
  after: Vec3;
  skin: Vec3;
  white: Vec3 | null;
}

/** 두 화장을 한 바탕에 올린 결과. 색은 Lab이다. along은 사용자 효과를 목표 효과 방향에 투영한 길이 ÷ 목표 효과 길이 */
export interface Comparison {
  base: Vec3;
  reference: Vec3;
  user: Vec3;
  same: number;
  ratio: number;
  along: number;
  /** mix에서만 낸 바른 양의 비율(사용자 ÷ 레퍼런스). 다른 방법은 NaN */
  amount: number;
}

/** 화장 종류마다 고른 맞추기 방법 */
export const methodFor = (makeup: string): MatchMethod =>
  DARK_MAKEUPS.includes(makeup) ? DARK_METHOD : COLOR_METHOD;

/** 바르기 전 색에 change만큼 바뀌려면 적어도 얼마나 발라야 하는지(0~1) */
export function leastPaint(before: Vec3, change: Vec3): number {
  const need = Math.max(
    ...change.map((c, i) =>
      c < 0 ? -c / Math.max(before[i], TINY) : c / Math.max(1 - before[i], TINY),
    ),
  );
  return Math.min(Math.max(need, LEAST_PAINT_MIN), 1);
}

function result(base: Vec3, reference: Vec3, user: Vec3): Omit<Comparison, "amount"> {
  const refSize = de(base, reference);
  const userSize = de(base, user);
  const refStep = sub(reference, base);
  const length = dot(refStep, refStep);
  return {
    base,
    reference,
    user,
    same: de(reference, user),
    ratio: refSize > 0 ? userSize / refSize : NaN,
    along: length > 0 ? dot(sub(user, base), refStep) / length : NaN,
  };
}

function anchorOf(side: AreaSide, anchor: "skin" | "white"): Vec3 {
  if (anchor === "skin") return side.skin;
  if (!side.white) throw new Error("흰자 기준 방법인데 흰자 색이 없다");
  return side.white;
}

/** mix 안료를 사용자 화면으로 옮길 채널별 배수. chroma는 흰자의 밝기 차이를 제외하고 색만 맞춘다 */
export function anchorGain(
  reference: Vec3,
  user: Vec3,
  method: Extract<MatchMethod, { name: "mix" }>,
): Vec3 {
  const ref = map3(reference, (v) => Math.max(v, TINY));
  const current = map3(user, (v) => Math.max(v, TINY));
  const light = method.degree === "chroma" ? dot(current, LUMA) / dot(ref, LUMA) : 1;
  return map3(current, (v, i) => (v / ref[i] / light) ** method.weight);
}

function mix(reference: AreaSide, user: AreaSide, method: Extract<MatchMethod, { name: "mix" }>) {
  const refChange = sub(reference.after, reference.before);
  const refAmount = leastPaint(reference.before, refChange);
  const pigment = map3(reference.before, (b, i) => b + refChange[i] / refAmount);
  const userAnchor = anchorOf(user, method.anchor);
  const refAnchor = anchorOf(reference, method.anchor);
  const gain = anchorGain(refAnchor, userAnchor, method);
  const toward = map3(pigment, (p, i) => gain[i] * p - user.before[i]);
  const length = Math.max(dot(toward, toward), TINY);
  const userAmount = Math.max(dot(sub(user.after, user.before), toward) / length, 0);
  const target = map3(user.before, (b, i) => b + refAmount * toward[i]);
  return {
    ...result(labOf(user.before), labOf(clip0(target)), labOf(user.after)),
    amount: userAmount / refAmount,
  };
}

function pick(reference: Vec3, user: Vec3, target: "reference" | "user" | "average"): Vec3 {
  if (target === "reference") return reference;
  if (target === "user") return user;
  return map3(reference, (r, i) => Math.sqrt(Math.max(r, 0) * Math.max(user[i], 0)));
}

/** 바탕 색에 그 화면의 바른 뒤 ÷ 바르기 전 배수를 채널마다 곱한다 */
const local = (side: AreaSide, base: Vec3) =>
  map3(base, (b, i) => (side.after[i] / Math.max(side.before[i], TINY)) * b);

/** 레퍼런스 화장과 사용자 화장을 method로 맞춰 한 바탕 위에서 견준다 */
export function compare(reference: AreaSide, user: AreaSide, method: MatchMethod): Comparison {
  if (method.name === "mix") return mix(reference, user, method);
  const base = pick(reference.before, user.before, method.target);
  return {
    ...result(labOf(base), labOf(local(reference, base)), labOf(local(user, base))),
    amount: NaN,
  };
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(mid)] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** 칸 색 표 여러 장의 칸마다 가운데 값. NaN은 그 장만 빼고, 모두 NaN이면 NaN이다 */
export function framesMedian(grids: CellLab[]): CellLab {
  const out = new Float32Array(GRID * GRID * 3).fill(NaN);
  // 0.2초마다 부르므로 칸마다 배열을 만들지 않고 몇 장뿐인 값을 끼워 넣어 정렬한다
  const values = new Float64Array(grids.length);
  for (let i = 0; i < out.length; i++) {
    let n = 0;
    for (const g of grids) {
      const v = g[i];
      if (Number.isNaN(v)) continue;
      let j = n++;
      while (j > 0 && values[j - 1] > v) values[j] = values[--j];
      values[j] = v;
    }
    if (n) out[i] = n % 2 ? values[(n - 1) / 2] : (values[n / 2 - 1] + values[n / 2]) / 2;
  }
  return out;
}

/** 가이드 결과 gauge에서 레퍼런스 쪽 AreaSide를 만든다. 바르기 전 색은 바른 뒤 색 − effect.delta */
export function referenceSide(gauge: GaugeReference | null | undefined): AreaSide | null {
  if (!gauge?.color || !gauge.effect) return null;
  const after = gauge.color.lab;
  const delta = gauge.effect.delta;
  const before = clip0(linearOfLab(map3(after, (v, i) => v - delta[i])));
  return {
    before,
    after: clip0(linearOfLab(after)),
    skin: before,
    white: gauge.white ? linearOfHex(gauge.white.hex) : null,
  };
}

/** 영역 칸의 기준 색 · 지금 색 가운데 값(Lab)으로 사용자 쪽 AreaSide를 만든다. 칸이 모자라면 null */
export function userSideOfLab(
  before: Vec3,
  after: Vec3,
  cells: number,
  white: Vec3 | null,
): AreaSide | null {
  if (cells < MIN_AREA_CELLS) return null;
  const beforeLinear = clip0(linearOfLab(before));
  return { before: beforeLinear, after: clip0(linearOfLab(after)), skin: beforeLinear, white };
}

/**
 * 영역 하나의 사용자 쪽 AreaSide와 잰 칸 수. current는 최근 칸 색의 가운데 값, start는 단계 시작 기준,
 * area는 영역 칸, made는 그 단계 영역 칸 전체(조명 재기에서 뺌), white는 맨얼굴 기준 흰자 색이다.
 * 묶음이 여럿이면 조명 변화(light)를 한 번 내서 넘긴다
 */
export function userSide(
  current: CellLab,
  start: Baseline,
  area: Uint8Array,
  made: Uint8Array | null,
  white: Vec3 | null,
  light: CellLab = lightChange(current, start, made),
): { side: AreaSide | null; cells: number } {
  const keys: number[] = [];
  for (let k = 0; k < GRID * GRID; k++) {
    const known = [0, 1, 2].every((ch) => !Number.isNaN(current[k * 3 + ch]));
    if (area[k] && start.cells[k] && known) keys.push(k);
  }
  const lab = (fn: (k: number, ch: number) => number) =>
    [0, 1, 2].map((ch) => median(keys.map((k) => fn(k, ch)))) as Vec3;
  if (keys.length < MIN_AREA_CELLS) return { side: null, cells: keys.length };
  const before = lab((k, ch) => start.lab[k * 3 + ch]);
  const after = lab((k, ch) => current[k * 3 + ch] - light[k * 3 + ch]);
  return { side: userSideOfLab(before, after, keys.length, white), cells: keys.length };
}

/** 영역 하나(좌우 짝이면 한쪽)를 잰 값. 못 쟀으면 값은 null이고 reason에 이유가 든다 */
export interface SideMeasure {
  region: string | null;
  /** 진하기 비율. 1이면 레퍼런스만큼. 색조 제품은 목표축을 따라 변한 양의 절댓값 */
  ratio: number | null;
  /** 색상 각도 차이(도). 노란 쪽이 + */
  hue: number | null;
  /** 채도 차이. +면 더 선명 */
  chroma: number | null;
  cells: number;
  reason: MeasureReason | null;
  /** 목표 효과 크기(바탕에서 목표 색까지 ΔE2000) */
  target: number | null;
}

/** 하위 단계 하나의 게이지 값 */
export interface Measure {
  ratio: number | null;
  /** 게이지 막대 0~BAR.max. 위치선은 BAR.atReference */
  bar: number | null;
  hue: number | null;
  chroma: number | null;
  hueSame: boolean | null;
  chromaSame: boolean | null;
  target: number | null;
  sides: SideMeasure[];
  reason: MeasureReason | null;
}

/** 영역 묶음 하나의 입력. side가 null이면 칸이 모자란 것이다 */
export interface SideInput {
  region: string | null;
  side: AreaSide | null;
  cells: number;
}

const failed = (region: string | null, cells: number, reason: MeasureReason): SideMeasure => ({
  region,
  ratio: null,
  hue: null,
  chroma: null,
  cells,
  reason,
  target: null,
});

/** 바탕에서 목표 색 쪽으로 사용자 효과만큼(Lab 길이) 간 색 */
function matchedTarget(result: Comparison): Vec3 {
  const target = sub(result.reference, result.base);
  const scale = norm(sub(result.user, result.base)) / Math.max(norm(target), TINY);
  return map3(result.base, (b, i) => b + scale * target[i]);
}

/** 맞춘 두 화장의 색감 차이. 효과가 거의 없으면 둘 다 NaN, 목표 효과 a · b가 작으면 hue만 NaN */
export function colorShift(result: Comparison): { hue: number; chroma: number } {
  const target = sub(result.reference, result.base);
  const user = result.user;
  const moved = norm(target) > TINY && norm(sub(user, result.base)) > TINY;
  if (!moved) return { hue: NaN, chroma: NaN };
  const matched = matchedTarget(result);
  const turn =
    ((Math.atan2(user[2], user[1]) - Math.atan2(matched[2], matched[1])) * 180) / Math.PI;
  const colored = Math.hypot(target[1], target[2]) >= COLOR.hueMinChroma;
  return {
    hue: colored ? ((((turn + 180) % 360) + 360) % 360) - 180 : NaN,
    chroma: Math.hypot(user[1], user[2]) - Math.hypot(matched[1], matched[2]),
  };
}

/** 영역 하나에서 레퍼런스와 사용자 화장을 맞춰 진하기 비율과 색감 차이를 낸다 */
export function measureSide(
  reference: AreaSide | null,
  user: AreaSide | null,
  makeup: string,
  cells: number,
  region: string | null = null,
  method: MatchMethod = methodFor(makeup),
): SideMeasure {
  if (!reference) return failed(region, cells, "noReference");
  if (!user) return failed(region, cells, "tooFewCells");
  if (method.name === "mix" && method.anchor === "white" && (!reference.white || !user.white))
    return failed(region, cells, "noWhite");
  const result = compare(reference, user, method);
  if (Number.isNaN(result.along)) return failed(region, cells, "noReference");
  const ratio = DARK_MAKEUPS.includes(makeup) ? Math.max(result.along, 0) : Math.abs(result.along);
  const target = de(result.reference, result.base);
  if (DARK_MAKEUPS.includes(makeup))
    return { region, ratio, hue: null, chroma: null, cells, reason: null, target };
  const { hue, chroma } = colorShift(result);
  return {
    region,
    ratio,
    hue: Number.isNaN(hue) ? null : hue,
    chroma: Number.isNaN(chroma) ? null : chroma,
    cells,
    reason: null,
    target,
  };
}

/** 진하기 비율을 게이지 막대(0~BAR.max)로. 1이면 위치선(BAR.atReference) */
export const gaugeBar = (ratio: number) => Math.min(Math.max(ratio * BAR.atReference, 0), BAR.max);

/** 하위 단계 하나의 게이지 값. 좌우를 따로 재고 combine으로 고른다(weaker면 덜 바른 쪽) */
export function measure(
  gauge: GaugeReference | null | undefined,
  makeup: string,
  sides: SideInput[],
  combine: Combine = COMBINE,
): Measure {
  const empty = {
    ratio: null,
    bar: null,
    hue: null,
    chroma: null,
    hueSame: null,
    chromaSame: null,
  };
  if (THIN_MAKEUPS.includes(makeup))
    return { ...empty, target: null, sides: [], reason: "thinArea" };
  const reference = referenceSide(gauge);
  const measured = sides.map((s) => measureSide(reference, s.side, makeup, s.cells, s.region));
  const valid = measured.filter((s) => s.ratio !== null);
  if (!valid.length) {
    const reason = measured.find((s) => s.reason)?.reason ?? "noReference";
    return { ...empty, target: null, sides: measured, reason };
  }
  // 같은 값이면 앞쪽을 고른다(Python min · max와 같음)
  const chosen = valid.reduce((best, s) =>
    combine === "stronger"
      ? s.ratio! > best.ratio!
        ? s
        : best
      : s.ratio! < best.ratio!
        ? s
        : best,
  );
  const ratio =
    combine === "mean" ? valid.reduce((sum, s) => sum + s.ratio!, 0) / valid.length : chosen.ratio!;
  return {
    ratio,
    bar: gaugeBar(ratio),
    hue: chosen.hue,
    chroma: chosen.chroma,
    hueSame: chosen.hue === null ? null : Math.abs(chosen.hue) <= COLOR.hueSameDegrees,
    chromaSame: chosen.chroma === null ? null : Math.abs(chosen.chroma) <= COLOR.chromaSame,
    target: chosen.target,
    sides: measured,
    reason: null,
  };
}
