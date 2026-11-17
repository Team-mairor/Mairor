import { describe, expect, it } from "vitest";

import {
  frameReason,
  GaugeStabilizer,
  HOLD_MS,
  nextStartPicks,
  windowReason,
  type FrameReason,
  type GaugeDisplay,
  type GaugeReason,
} from "./stability";
import spec from "../../../../shared/gauge/stability.v1.json" with { type: "json" };

/** 기대값은 소수 넷째 자리로 반올림해 적었으므로 같이 반올림해 견준다 */
const closeOrNull = (actual: number | null, expected: number | null) => {
  if (expected === null) expect(actual).toBeNull();
  else expect(Number(actual?.toFixed(4))).toBeCloseTo(expected, 4);
};

describe("frameReason", () => {
  it.each(spec.frames.map((c) => [c.name, c] as const))("%s", (_, c) => {
    expect(frameReason(c.state, c.makeup)).toBe(c.expected);
  });
});

describe("windowReason", () => {
  it.each(spec.windows.map((c) => [c.name, c] as const))("%s", (_, c) => {
    expect(windowReason(c.reasons as (FrameReason | null)[])).toBe(c.expected);
  });
});

describe("GaugeStabilizer", () => {
  it.each(spec.sequences.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const stabilizer = new GaugeStabilizer();
    const shown: GaugeDisplay[] = c.ticks.map((tick) =>
      stabilizer.update(
        tick.t,
        tick.ratio === null ? null : tick,
        tick.reason as GaugeReason | null,
      ),
    );
    expect(shown).toHaveLength(c.expected.length);
    shown.forEach((got, i) => {
      const want = c.expected[i];
      closeOrNull(got.ratio, want.ratio);
      closeOrNull(got.bar, want.bar);
      expect({ ...got, ratio: 0, bar: 0 }).toEqual({ ...want, ratio: 0, bar: 0 });
    });
  });

  it("마지막 위치 유지 옵션이면 측정 중단이 길어져도 값을 숨기지 않는다", () => {
    const stabilizer = new GaugeStabilizer(true);
    const measured = stabilizer.update(0, {
      ratio: 1,
      target: null,
      hueSame: true,
      chromaSame: true,
    });
    const stopped = stabilizer.update(HOLD_MS + 1, null, "lost");

    expect(stopped).toMatchObject({
      ratio: measured.ratio,
      bar: measured.bar,
      stale: true,
      reason: "lost",
    });
  });
});

describe("nextStartPicks", () => {
  const times = [0, 500, 1000, 1500, 2000, 2500, 3000];

  it("직전 창 안에서 쓸 수 있는 사진만 고른다", () => {
    const reasons: (FrameReason | null)[] = [null, null, null, "covered", null, null, null];
    expect(nextStartPicks(times, reasons, 3000)).toEqual([2, 4, 5, 6]);
  });

  it("모자라면 null", () => {
    const reasons: (FrameReason | null)[] = [null, null, "covered", null, "lost", "turned", null];
    expect(nextStartPicks(times, reasons, 3000)).toBeNull();
  });
});
