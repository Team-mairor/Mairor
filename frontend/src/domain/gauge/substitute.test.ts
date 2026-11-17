import { describe, expect, it } from "vitest";

import type { GaugeReference } from "@/vision/guide";

import { linearOfSrgb, userSideOfLab, type Vec3 } from "./measure";
import { measureForProduct, productRule, type SelectedProduct } from "./substitute";
import raw from "../../../../shared/gauge/substitute.v1.json" with { type: "json" };

type Case = (typeof raw.cases)[number];

const hexRgb = (hex: string): Vec3 =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Vec3;

/** 시험 데이터의 레퍼런스 입력(lab · delta · white)을 가이드 결과 gauge 모양으로 바꾼다 */
function gaugeOf(reference: Case["reference"]): GaugeReference | null {
  if (!reference) return null;
  return {
    color: { hex: "#000000", lab: reference.lab as Vec3 },
    effect: { delta: reference.delta as Vec3, size: 1, direction: "darker" },
    strength: 0,
    reason: null,
    white: reference.white ? { hex: reference.white, lab: [0, 0, 0] } : null,
  };
}

const closeOrNull = (actual: number | null | undefined, expected: number | null) => {
  if (expected === null) expect(actual ?? null).toBeNull();
  else expect(actual).toBeCloseTo(expected, 4);
};

describe("고른 제품에 따른 게이지는 AI 기대값과 같다", () => {
  it.each(raw.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const gauge = gaugeOf(c.reference);
    const product = c.product as SelectedProduct;
    const rule = productRule(gauge, c.makeup, product);
    const want = c.expected;
    expect(rule.show).toBe(want.show);
    expect(rule.color).toBe(want.color);
    expect(rule.hideReason).toBe(want.hideReason);
    expect(rule.colorReason).toBe(want.colorReason);
    expect(rule.basis).toBe(want.basis);
    closeOrNull(rule.near, want.near);

    const sides = c.sides.map((s) => ({
      region: s.region,
      side: userSideOfLab(
        s.before as Vec3,
        s.after as Vec3,
        s.cells,
        s.white ? linearOfSrgb(hexRgb(s.white)) : null,
      ),
      cells: s.cells,
    }));
    const { measure } = measureForProduct(gauge, c.makeup, sides, product, rule);
    if (!want.measure) {
      expect(measure).toBeNull();
      return;
    }
    closeOrNull(measure?.ratio, want.measure.ratio);
    closeOrNull(measure?.bar, want.measure.bar);
    closeOrNull(measure?.hue, want.measure.hue);
    closeOrNull(measure?.chroma, want.measure.chroma);
    expect(measure?.hueSame ?? null).toBe(want.measure.hueSame);
    expect(measure?.chromaSame ?? null).toBe(want.measure.chromaSame);
    expect(measure?.reason ?? null).toBe(want.measure.reason);
  });
});
