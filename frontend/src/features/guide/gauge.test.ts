import { describe, expect, it } from "vitest";

import { gaugeOf, stepGauge } from "./gauge";
import type { AreaSubStep, GaugeReference } from "./types";

const lip: GaugeReference = {
  color: { hex: "#D77F7E", lab: [62.62, 33.87, 15.3] },
  effect: { delta: [-3.96, 9.13, 2.76], size: 5.18, direction: "darker" },
  strength: 25.9,
  reason: null,
  white: null,
};
const none: GaugeReference = {
  color: null,
  effect: null,
  strength: null,
  reason: "noArea",
  white: null,
};
const sub = (order: number, gauge?: GaugeReference | null): AreaSubStep => ({
  subStepId: `s1-${order}`,
  order,
  status: "extracted",
  reasons: [],
  templateId: null,
  guideSets: [],
  ...(gauge === undefined ? {} : { gauge }),
});

describe("게이지 기준 읽기", () => {
  it("계약 모양의 기준과 값을 못 낸 기준을 받는다", () => {
    expect(gaugeOf(lip)).toEqual(lip);
    expect(gaugeOf(none)).toEqual(none);
  });

  it("없거나 모양이 틀리면 기준 없음이다", () => {
    expect(gaugeOf(undefined)).toBeNull();
    expect(gaugeOf(null)).toBeNull();
    expect(gaugeOf({ ...lip, color: { hex: "red", lab: [1, 2, 3] } })).toBeNull();
    expect(gaugeOf({ ...lip, effect: { ...lip.effect, direction: "up" } })).toBeNull();
    expect(gaugeOf({ ...lip, effect: { ...lip.effect, size: Number.NaN } })).toBeNull();
    expect(gaugeOf({ ...lip, strength: "26" })).toBeNull();
  });

  it("흰자 색은 있으면 그대로 두고, 없거나 모양이 틀리면 null로 둔다", () => {
    const white = { hex: "#C3A8A2", lab: [71.02, 8.84, 6.73] };
    expect(gaugeOf({ ...lip, white })?.white).toEqual(white);
    const beforeWhite: Record<string, unknown> = { ...lip };
    delete beforeWhite.white;
    expect(gaugeOf(beforeWhite)?.white).toBeNull();
    expect(gaugeOf({ ...lip, white: { hex: "white" } })?.white).toBeNull();
  });
});

describe("단계 게이지 기준", () => {
  it("값이 있는 첫 하위 단계의 기준을 쓴다", () => {
    expect(stepGauge([sub(2, lip), sub(1, none)])).toEqual({ subStepId: "s1-2", gauge: lip });
  });

  it("기준을 넣기 전 결과, 이유가 있는 기준, 효과가 0인 기준뿐이면 게이지를 숨긴다", () => {
    const zero = { ...lip, effect: { ...lip.effect!, size: 0 } };
    expect(stepGauge([sub(1), sub(2, null), sub(3, none), sub(4, zero)])).toBeNull();
    expect(stepGauge([])).toBeNull();
  });
});
