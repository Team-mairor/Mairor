// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StepEvaluation } from "@/domain/gauge";

import { StepFeedback } from "./step-feedback";
import { FEEDBACK_MS, useStepFeedback } from "./use-step-feedback";

let root: Root;
let element: HTMLDivElement;
let current: ReturnType<typeof useStepFeedback>;
const api = () => current;
const keep = (feedback: ReturnType<typeof useStepFeedback>) => {
  current = feedback;
};

const nothing = { coverage: null, overflow: null };
const sides = { up: nothing, down: nothing, inner: nothing, outer: nothing };

/** 립을 거의 바르지 않은 평가(덮음 0.1) */
const thinLip = (subStepId: string): StepEvaluation => ({
  subStepId,
  makeup: "lip",
  coverage: 0.1,
  overflow: 0,
  sides,
  ratio: null,
  ratioReason: "noReference",
  regions: [
    { region: "lipsOuter", coverage: 0.1, overflow: 0, sides, cells: 100, band: 100, reason: null },
  ],
  reason: null,
  drift: 0,
});

function Probe({
  runId = "run",
  onApi = keep,
}: {
  runId?: string;
  onApi?: (feedback: ReturnType<typeof useStepFeedback>) => void;
}) {
  const feedback = useStepFeedback(runId);
  useEffect(() => onApi(feedback));
  return <StepFeedback lines={feedback.lines} onDismiss={feedback.dismiss} />;
}

const render = async (node: React.ReactNode) => {
  await act(async () => root.render(node));
};
const text = () => element.textContent ?? "";

beforeEach(() => {
  vi.useFakeTimers();
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});

afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.useRealTimers();
});

describe("튜토리얼 단계 끝 안내 문장", () => {
  it("묶음을 보이기 전에는 아무것도 띄우지 않는다", async () => {
    await render(<Probe />);
    act(() => api().record(0, thinLip("s0")));
    expect(text()).toBe("");
  });

  it("묶음 사진 뒤 그 묶음의 평가를 문장으로 띄우고 몇 초 뒤 지운다", async () => {
    await render(<Probe />);
    act(() => api().record(0, thinLip("s0")));
    act(() => api().show(0, 1));
    expect(text()).toContain("립을 조금 더 발라 주세요");
    expect(text()).not.toMatch(/\d/);
    act(() => void vi.advanceTimersByTime(FEEDBACK_MS - 1));
    expect(text()).toContain("립을");
    act(() => void vi.advanceTimersByTime(2));
    expect(text()).toBe("");
  });

  it("평가가 없는 묶음은 아무것도 띄우지 않는다", async () => {
    await render(<Probe />);
    act(() => api().show(0, 3));
    expect(text()).toBe("");
  });

  it("쓴 평가는 비워 다음 묶음에 이어지지 않는다", async () => {
    await render(<Probe />);
    act(() => api().record(0, thinLip("s0")));
    act(() => api().show(0, 1));
    act(() => api().show(0, 1));
    expect(text()).toBe("");
  });

  it("닫기 버튼을 누르면 닫힌다", async () => {
    await render(<Probe />);
    act(() => api().record(0, thinLip("s0")));
    act(() => api().show(0, 1));
    await act(async () => element.querySelector("button")?.click());
    expect(text()).toBe("");
  });

  it("상자는 터치를 통과시키고 닫기 버튼만 눌린다", async () => {
    await render(<Probe />);
    act(() => api().record(0, thinLip("s0")));
    act(() => api().show(0, 1));
    const box = element.querySelector('[data-testid="step-feedback"]');
    const buttons = element.querySelectorAll("button");
    expect(box?.classList.contains("pointer-events-none")).toBe(true);
    expect(buttons).toHaveLength(1);
    expect(buttons[0].classList.contains("pointer-events-auto")).toBe(true);
  });

  it("다른 실행으로 바뀌면 남은 문장과 평가를 버린다", async () => {
    await render(<Probe runId="a" />);
    act(() => api().record(0, thinLip("s0")));
    await render(<Probe runId="b" />);
    act(() => api().show(0, 1));
    expect(text()).toBe("");
  });
});
