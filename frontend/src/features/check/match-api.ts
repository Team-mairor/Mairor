"use client";

import { useEffect, useState } from "react";

import { api, errorMessage, isAbortError } from "@/lib/api";

/** NONE일 때 이유. NO_ITEMS 파우치 비어 있음, COMPARISON_UNAVAILABLE 비교할 기준색 없음, NO_SUITABLE_ITEM 맞는 종류·색 없음 */
export type NoneReason = "NO_ITEMS" | "COMPARISON_UNAVAILABLE" | "NO_SUITABLE_ITEM";

/** 단계별 매칭 결과. SAME은 같은 제품·호수 보유, SUBSTITUTE는 색이 가까운 대체 후보(최대 3개, 가까운 순) */
export interface StepMatch {
  stepId: string;
  result: "SAME" | "SUBSTITUTE" | "NONE";
  samePouchItemId: string | null;
  noneReason: NoneReason | null;
  candidates: { pouchItemId: string; rank: number }[];
}

/** POST /v1/users/me/guide-matches 응답. 화장 종류가 기타인 단계는 steps에 없다 */
export interface GuideMatch {
  matchId: string;
  guideId: string;
  steps: StepMatch[];
}

export type MatchLoad =
  | { status: "loading" }
  | { status: "ready"; byStep: Map<string, StepMatch> }
  | { status: "error"; message: string };

/**
 * 가이드와 내 파우치를 서버에서 맞춰 본다. 파우치가 바뀌면(pouchKey) 새로 맞춘다.
 * 매칭은 만든 때의 스냅샷이라 다시 조회하지 않고 새로 만든다
 */
export function useGuideMatch(guideId: string | null, pouchKey: string) {
  const [load, setLoad] = useState<MatchLoad>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!guideId) return;
    const ctrl = new AbortController();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 새로 맞추는 동안 이전 결과를 쓰지 않는다
    setLoad({ status: "loading" });
    api
      .post<GuideMatch>("/v1/users/me/guide-matches", { body: { guideId }, signal: ctrl.signal })
      .then((m) => setLoad({ status: "ready", byStep: new Map(m.steps.map((s) => [s.stepId, s])) }))
      .catch((e) => {
        if (!isAbortError(e)) setLoad({ status: "error", message: errorMessage(e) });
      });
    return () => ctrl.abort();
  }, [guideId, pouchKey, attempt]);

  return { load, retry: () => setAttempt((n) => n + 1) };
}
