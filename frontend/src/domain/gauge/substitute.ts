// 고른 제품(같은 제품 · 대체 제품 · 제품 없음)에 따라 게이지와 색감을 보일지 정한다.
// 값은 AI(Python)와 같이 쓰도록 shared/gauge/substitute.v1.json에 둔다.
import type { GaugeReference } from "@/vision/guide";

import { deltaE2000 } from "./color";
import { labOf, linearOfHex, linearOfLab, measure, type Measure, type SideInput } from "./measure";
import raw from "../../../../shared/gauge/substitute.v1.json" with { type: "json" };

export type Matching = "SAME" | "SUBSTITUTE" | "NONE";
export type HideReason = "noProduct";
export type ColorReason = "farColor" | "estimatedColor" | "noColor";
/** 진하기를 잴 기준. reference는 가이드 결과 gauge, product는 대체 제품 색 쪽으로 옮긴 기준이다 */
export type Basis = "reference" | "product";

/** 실행 단계 스냅샷에서 고른 제품 */
export interface SelectedProduct {
  result: Matching | null;
  selectedColor: {
    colorSpace?: string;
    hex: string | null;
    source?: string | null;
    estimated?: boolean;
  } | null;
  skipped?: boolean;
}

/** 가이드 결과 gauge 중 대체 제품 색을 견줄 때 쓰는 값 */
export interface ProductGauge {
  color: { lab: readonly [number, number, number] } | null;
  effect: { delta: readonly [number, number, number] } | null;
}

/**
 * show가 거짓이면 게이지를 숨기고, color가 거짓이면 진하기만 보인다.
 * near는 대체 제품일 때 잰 값이다(못 쟀으면 null). basis는 진하기를 잴 기준이다
 */
export interface ProductRule {
  show: boolean;
  color: boolean;
  near: number | null;
  hideReason: HideReason | null;
  colorReason: ColorReason | null;
  basis: Basis;
}

export const HIDE_RESULTS: readonly string[] = raw.hide.results;
export const HIDE_SKIPPED: boolean = raw.hide.skipped;
/** 대체 제품 색감을 보이는 near(ΔE2000) 상한 */
export const NEAR_COLOR_MAX: number = raw.color.nearMax;
export const TOWARD_STEPS: number = raw.color.towardSteps;
export const HIDE_ESTIMATED: boolean = raw.color.hideEstimated;
export const DARK_MAKEUPS: readonly string[] = raw.color.darkMakeups;

type Vec = [number, number, number];

const clip = (v: Vec): Vec => v.map((x) => Math.max(x, 0)) as Vec;
const de = (p: Vec, q: Vec) => deltaE2000(p[0], p[1], p[2], q[0], q[1], q[2]);

/**
 * 레퍼런스 바르기 전 색에서 제품 색 쪽으로 레퍼런스 효과와 같은 ΔE2000만큼 간 색(선형 RGB).
 * 제품 색까지 가도 못 미치면 제품 색이다
 */
export function towardColor(gauge: ProductGauge | null, hex: string): Vec | null {
  if (!gauge?.color || !gauge.effect) return null;
  const afterLab: Vec = [...gauge.color.lab];
  const delta = gauge.effect.delta;
  const before = clip(linearOfLab(afterLab.map((v, i) => v - delta[i]) as Vec));
  const after = clip(linearOfLab(afterLab));
  const product = linearOfHex(hex);
  const beforeLab = labOf(before);
  const target = de(beforeLab, labOf(after));
  if (de(beforeLab, labOf(product)) < target) return product;
  const at = (t: number) => before.map((b, i) => b + t * (product[i] - b)) as Vec;
  let low = 0;
  let high = 1;
  for (let k = 0; k < TOWARD_STEPS; k++) {
    const middle = (low + high) / 2;
    if (de(beforeLab, labOf(at(middle))) < target) low = middle;
    else high = middle;
  }
  return at((low + high) / 2);
}

/** 대체 제품 색이 레퍼런스와 얼마나 다른지: towardColor와 레퍼런스 바른 뒤 색의 ΔE2000 */
export function colorNear(gauge: ProductGauge | null, hex: string): number | null {
  const toward = towardColor(gauge, hex);
  if (!toward || !gauge?.color) return null;
  return de([...gauge.color.lab], labOf(clip(toward)));
}

const rule = (
  show: boolean,
  color: boolean,
  near: number | null = null,
  colorReason: ColorReason | null = null,
  basis: Basis = "reference",
): ProductRule => ({
  show,
  color,
  near,
  hideReason: show ? null : "noProduct",
  colorReason,
  basis,
});

/** 고른 제품으로 게이지를 보일지, 무엇을 기준으로 잴지, 색감을 보일지 정한다. 하위 단계마다 한 번 부르면 된다 */
export function productRule(
  gauge: ProductGauge | null,
  makeup: string,
  product: SelectedProduct,
): ProductRule {
  const result = product.result ?? "NONE";
  if (HIDE_RESULTS.includes(result) || (HIDE_SKIPPED && product.skipped)) return rule(false, false);
  if (result === "SAME") return rule(true, true);
  const colored = !DARK_MAKEUPS.includes(makeup);
  const hex = product.selectedColor?.hex;
  if (!hex) return rule(true, false, null, colored ? "noColor" : null);
  const near = colorNear(gauge, hex);
  if (near === null) return rule(true, false);
  const basis: Basis = near <= NEAR_COLOR_MAX ? "reference" : "product";
  if (!colored) return rule(true, false, near, null, basis);
  if (HIDE_ESTIMATED && product.selectedColor?.estimated)
    return rule(true, false, near, "estimatedColor", basis);
  if (basis === "product") return rule(true, false, near, "farColor", basis);
  return rule(true, true, near, null, basis);
}

/**
 * 대체 제품 색 쪽으로 옮긴 기준: towardColor를 바른 뒤 색으로 둔 gauge. 바르기 전 색은 그대로라
 * effect.delta도 그 차이로 바뀌고, 가이드 결과처럼 소수 둘째 자리다. 흰자 등 다른 칸은 그대로다
 */
export function substituteReference<G extends ProductGauge>(gauge: G, hex: string): G | null {
  const toward = towardColor(gauge, hex);
  if (!toward || !gauge.color || !gauge.effect) return null;
  const round2 = (v: number) => Math.round(v * 100) / 100;
  const after = labOf(clip(toward));
  const before = gauge.color.lab.map((v, i) => v - gauge.effect!.delta[i]);
  return {
    ...gauge,
    color: { ...gauge.color, lab: after.map(round2) as Vec },
    effect: { ...gauge.effect, delta: after.map((v, i) => round2(v - before[i])) as Vec },
  };
}

/** 고른 제품을 반영한 게이지 값. 게이지를 숨기면 measure는 null이다 */
export interface ProductMeasure {
  rule: ProductRule;
  measure: Measure | null;
}

/**
 * measure에 고른 제품 규칙을 더한다. basis가 product이면 대체 제품 쪽으로 옮긴 기준으로 재고,
 * 색감을 보이지 않으면 hue · chroma를 지운다
 */
export function measureForProduct(
  gauge: GaugeReference | null,
  makeup: string,
  sides: SideInput[],
  product: SelectedProduct,
  given: ProductRule = productRule(gauge, makeup, product),
): ProductMeasure {
  if (!given.show) return { rule: given, measure: null };
  const hex = product.selectedColor?.hex;
  const basis = given.basis === "product" && gauge && hex ? substituteReference(gauge, hex) : gauge;
  const out = measure(basis, makeup, sides);
  if (given.color) return { rule: given, measure: out };
  return {
    rule: given,
    measure: {
      ...out,
      hue: null,
      chroma: null,
      hueSame: null,
      chromaSame: null,
      sides: out.sides.map((side) => ({ ...side, hue: null, chroma: null })),
    },
  };
}
