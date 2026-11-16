import { describe, expect, it } from "vitest";

import type { GaugeReference } from "@/features/guide";

import { linearOfSrgb, measure, type SideMeasure, userSideOfLab, type Vec3 } from "./measure";
import spec from "../../../../shared/gauge/measure.v1.json" with { type: "json" };

type Case = (typeof spec.cases)[number];

const hexRgb = (hex: string): Vec3 =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Vec3;

/** 시험 데이터의 레퍼런스 입력을 가이드 결과 gauge로 */
function gaugeOf(reference: Case["reference"]): GaugeReference {
  if (!reference)
    return { color: null, effect: null, strength: null, reason: "noArea", white: null };
  return {
    color: { hex: "#000000", lab: reference.lab as Vec3 },
    effect: { delta: reference.delta as Vec3, size: 1, direction: "darker" },
    strength: 0,
    reason: null,
    white: reference.white ? { hex: reference.white, lab: [0, 0, 0] } : null,
  };
}

const closeOrNull = (actual: number | null, expected: number | null) => {
  if (expected === null) expect(actual).toBeNull();
  else expect(actual).toBeCloseTo(expected, 4);
};

describe("게이지 값 계산은 AI 기대값과 같다", () => {
  it.each(spec.cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
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
    const out = measure(gaugeOf(c.reference), c.makeup, sides);
    const want = c.expected;
    closeOrNull(out.ratio, want.ratio);
    closeOrNull(out.bar, want.bar);
    closeOrNull(out.hue, want.hue);
    closeOrNull(out.chroma, want.chroma);
    closeOrNull(out.target, want.target);
    expect(out.hueSame).toBe(want.hueSame);
    expect(out.chromaSame).toBe(want.chromaSame);
    expect(out.reason).toBe(want.reason);
    expect(out.sides).toHaveLength(want.sides.length);
    want.sides.forEach((w, i) => {
      const side: SideMeasure = out.sides[i];
      expect(side.region).toBe(w.region);
      closeOrNull(side.ratio, w.ratio);
      closeOrNull(side.hue, w.hue);
      closeOrNull(side.chroma, w.chroma);
      closeOrNull(side.target, w.target);
      expect(side.reason).toBe(w.reason);
    });
  });
});
