"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { bundleMessages, renderMessage, stepMessages, type StepEvaluation } from "@/domain/gauge";
import { useTimeout } from "@/lib/hooks/use-timeout";

/** 묶음 사진을 찍은 뒤 안내 문장을 띄워 두는 시간(ms) */
export const FEEDBACK_MS = 8000;

/**
 * 튜토리얼 단계 끝 안내 문장. 「다음」을 누를 때마다 그 단계의 평가를 모아 두었다가
 * 묶음 사진을 찍은 뒤 최대 3줄로 보여 준다. 점수 · 합격 · 숫자는 없고, 평가와 문장은 이번 실행 화면에만 두며
 * 보내거나 저장하지 않는다. 사용자가 누르거나 다음 묶음을 시작하거나 몇 초가 지나면 사라진다
 */
export function useStepFeedback(runId: string) {
  const evaluations = useRef(new Map<number, StepEvaluation>());
  const [lines, setLines] = useState<string[]>([]);
  const timer = useTimeout();

  // 다른 실행의 평가는 쓰지 않는다
  useEffect(() => {
    evaluations.current.clear();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 실행이 바뀌면 남은 문장을 지운다
    setLines([]);
    timer.clear();
  }, [runId, timer]);

  /** 그 단계의 평가를 남긴다. 같은 단계를 다시 넘기면 덮어쓴다 */
  const record = useCallback((step: number, evaluation: StepEvaluation) => {
    evaluations.current.set(step, evaluation);
  }, []);

  /** 묶음(from 이상 to 미만 단계)의 평가를 문장으로 바꿔 띄우고, 쓴 평가는 비운다 */
  const show = useCallback(
    (from: number, to: number) => {
      const steps = [];
      for (let i = from; i < to; i++) {
        const evaluation = evaluations.current.get(i);
        steps.push(evaluation ? stepMessages(evaluation, evaluation.makeup) : []);
        evaluations.current.delete(i);
      }
      const next = bundleMessages(steps).map(renderMessage);
      setLines(next);
      if (next.length) timer.set(() => setLines([]), FEEDBACK_MS);
    },
    [timer],
  );

  const dismiss = useCallback(() => {
    timer.clear();
    setLines([]);
  }, [timer]);

  return { lines, record, show, dismiss };
}
