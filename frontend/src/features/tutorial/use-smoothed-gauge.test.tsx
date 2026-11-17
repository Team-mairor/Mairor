// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  GAUGE_SMOOTH_MS,
  gaugeLabelIndex,
  useSmoothedGauge,
  type SmoothedGauge,
} from "./use-smoothed-gauge";

const probe: { current: SmoothedGauge | null } = { current: null };
function Probe({ bar }: { bar: number | null }) {
  const shown = useSmoothedGauge(bar);
  useEffect(() => {
    probe.current = shown;
  });
  return null;
}
const shown = () => probe.current!;

let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.useFakeTimers();
  root = createRoot(document.createElement("div"));
});
afterEach(async () => {
  await act(async () => root.unmount());
  vi.useRealTimers();
});

const render = (bar: number | null) => act(async () => root.render(<Probe bar={bar} />));
const advance = (ms: number) => act(async () => void vi.advanceTimersByTime(ms));

describe("게이지 표시 값 다듬기", () => {
  it("처음 값과 그 문구는 기다리지 않고 바로 보인다", async () => {
    await render(20);
    expect(shown()).toEqual({ bar: 20, label: "lighter" });
  });

  it("값이 바뀌면 정해진 시간에 걸쳐 따라가고 한참 지나면 새 값에 닿는다", async () => {
    await render(10);
    await render(60);
    await advance(100);
    expect(shown().bar).toBeGreaterThan(10);
    expect(shown().bar).toBeLessThan(15);

    await advance(GAUGE_SMOOTH_MS - 100);
    // 정해진 시간이 지나면 차이의 약 63%를 따라간다
    expect(shown().bar).toBeGreaterThan(10 + 50 * 0.55);
    expect(shown().bar).toBeLessThan(10 + 50 * 0.7);

    await advance(GAUGE_SMOOTH_MS * 10);
    expect(shown().bar).toBe(60);
    // 목표(50)를 막 넘어도 「비슷해요」이고, 55를 넘으면 「진해요」다
    expect(shown().label).toBe("darker");

    await render(50);
    await advance(GAUGE_SMOOTH_MS * 10);
    expect(shown()).toEqual({ bar: 50, label: "similar" });
  });

  it("짧게 출렁이는 값은 막대도 문구도 그대로 따라 흔들리지 않는다", async () => {
    await render(30);
    const bars: number[] = [];
    const labels = new Set<string | null>();
    for (const raw of [66, 34, 88, 33, 70, 37, 69, 36]) {
      await render(raw);
      await advance(1000);
      bars.push(shown().bar as number);
      labels.add(shown().label);
    }
    // 입력은 33~88로 폭이 55인데 보이는 막대는 훨씬 좁고, 문구는 한두 가지로 안정된다
    expect(Math.max(...bars) - Math.min(...bars)).toBeLessThan(25);
    expect(labels.size).toBeLessThanOrEqual(2);
  });

  it("측정값이 없어지면 바로 비운다", async () => {
    await render(30);
    await render(null);
    await advance(100);
    expect(shown()).toEqual({ bar: null, label: null });
  });

  it("문구 경계: 연해요 35 미만 · 비슷해요 35~55 · 진해요 55 초과, 되돌아올 때만 3점 완충", () => {
    expect([20, 34.9, 35, 50, 55, 55.1, 90].map((b) => gaugeLabelIndex(b, null))).toEqual([
      0, 0, 1, 1, 1, 2, 2,
    ]);
    // 올라갈 때는 경계를 넘는 순간 바뀐다
    expect(gaugeLabelIndex(35, 0)).toBe(1);
    expect(gaugeLabelIndex(55.1, 1)).toBe(2);
    // 내려올 때는 완충만큼 더 내려가야 바뀐다
    expect(gaugeLabelIndex(53, 2)).toBe(2);
    expect(gaugeLabelIndex(51.9, 2)).toBe(1);
    expect(gaugeLabelIndex(33, 1)).toBe(1);
    expect(gaugeLabelIndex(31.9, 1)).toBe(0);
  });
});
