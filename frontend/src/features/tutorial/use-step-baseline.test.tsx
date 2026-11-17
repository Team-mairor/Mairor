// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useStepBaseline } from "./use-step-baseline";

const mocks = vi.hoisted(() => ({
  frames: 0,
  restart: vi.fn(),
}));

vi.mock("@/features/gauge", () => ({
  useGaugeBaseline: () => ({
    status: { frames: mocks.frames, lock: { exposure: "고정됨" }, front: true },
    stepBaseline: () => null,
    restart: mocks.restart,
  }),
}));

type Gate = ReturnType<typeof useStepBaseline>;
const probe: { current: Gate | null } = { current: null };
function Probe({ step = 1 }: { step?: number }) {
  const gate = useStepBaseline({
    runId: "run",
    step,
    makeup: "blush",
    regions: undefined,
    ready: false,
    showGauge: true,
    exitAsk: false,
    paused: false,
    recordingNext: false,
  });
  useEffect(() => {
    probe.current = gate;
  });
  return null;
}
const gate = () => probe.current!;

let root: Root;
let element: HTMLDivElement;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.useFakeTimers();
  mocks.frames = 0;
  mocks.restart.mockClear();
  element = document.createElement("div");
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  vi.useRealTimers();
});

const advance = (ms: number) => act(async () => void vi.advanceTimersByTime(ms));
const render = (step?: number) => act(async () => root.render(<Probe step={step} />));

describe("단계 준비 기준 사진 멈춤", () => {
  it("사진이 1초 넘게 늘지 않으면 멈춘 것으로 본다", async () => {
    await render();
    await advance(900);
    expect(gate().stalled).toBe(false);
    await advance(200);
    expect(gate().stalled).toBe(true);
  });

  it("다시 모으면 정면을 다시 배우는 동안은 멈춘 것으로 보지 않고 그 뒤에도 안 모이면 다시 알린다", async () => {
    await render();
    await advance(1100);
    expect(gate().stalled).toBe(true);

    await act(async () => gate().retry());
    expect(mocks.restart).toHaveBeenCalledTimes(1);
    expect(gate().stalled).toBe(false);

    await advance(7000);
    expect(gate().stalled).toBe(false);
    await advance(1500);
    expect(gate().stalled).toBe(true);
  });

  it("다시 모은 뒤 사진이 늘기 시작하면 1초 기준으로 돌아간다", async () => {
    await render();
    await advance(1100);
    await act(async () => gate().retry());

    mocks.frames = 5;
    await render();
    await advance(900);
    expect(gate().stalled).toBe(false);
    await advance(200);
    expect(gate().stalled).toBe(true);
  });

  it("다른 단계에서는 이전 단계의 다시 모으기 유예를 쓰지 않는다", async () => {
    await render(1);
    await advance(1100);
    await act(async () => gate().retry());

    await render(2);
    await advance(1100);
    expect(gate().stalled).toBe(true);
  });
});
