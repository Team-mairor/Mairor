import { describe, expect, it } from "vitest";

import type { GaugeReference } from "@/features/guide";

import {
  anchorGain,
  COLOR_METHOD,
  linearOfSrgb,
  measure,
  type SideMeasure,
  userSideOfLab,
  type Vec3,
} from "./measure";
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
  it("공유 규격의 흰자 보정 범위를 따른다", () => {
    const reference: Vec3 = [0.8, 0.8, 0.8];
    const user: Vec3 = [0.4, 0.4, 0.4];
    const degree = "degree" in spec.methods.color ? spec.methods.color.degree : "full";
    expect(COLOR_METHOD).toMatchObject({ degree });
    expect(
      anchorGain(reference, user, COLOR_METHOD as Extract<typeof COLOR_METHOD, { name: "mix" }>),
    ).toEqual(degree === "chroma" ? [1, 1, 1] : [0.5, 0.5, 0.5]);
  });

  it("색조 제품은 목표축 반대 방향의 실제 색 변화도 바른 양으로 잰다", () => {
    const reference = spec.cases[0].reference;
    if (!reference) throw new Error("립 기준이 필요하다");
    const before = reference.lab.map((value, index) => value - reference.delta[index]) as Vec3;
    const opposite = before.map((value, index) => value - reference.delta[index] * 0.5) as Vec3;
    const side = userSideOfLab(
      before,
      opposite,
      120,
      reference.white ? linearOfSrgb(hexRgb(reference.white)) : null,
    );

    const out = measure(gaugeOf(reference), "lip", [{ region: "lipsOuter", side, cells: 120 }]);

    expect(out.ratio).not.toBeNull();
    expect(out.ratio!).toBeGreaterThan(0);
    expect(out.bar!).toBeGreaterThan(0);
  });

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
