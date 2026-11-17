"use client";

import type { PendingGuide } from "@/domain/session";
import { api, type AnalysisJobSummary, type Page } from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";

/** GET /v1/users/me/analysis-jobs?size=1 (API-VIDEO-007). 가장 최근에 끝난 내 분석(검수 중 · 승인) 하나 */
function latestAnalysis(_account: string, signal: AbortSignal) {
  return api.get<Page<AnalysisJobSummary>>("/v1/users/me/analysis-jobs", {
    query: { size: 1 },
    signal,
  });
}

/** account(로그인한 계정)가 바뀌면 다시 받고, null이면(로그인 확인 전 · 비로그인) 부르지 않는다 */
export const useLatestAnalysis = (account: string | null) => useLoad(account, latestAnalysis);

/**
 * 내 분석 한 줄을 홈 검수 카드로 바꾼다. 기기에 저장하는 카드(PendingGuide)와 같은 모양이라 홈은 어느 쪽이든 같은 카드로 그린다.
 * 승인됐는데 guideId가 없거나 반려면 카드를 띄우지 않는다
 */
export function toPendingGuide(s: AnalysisJobSummary): PendingGuide | null {
  const base = { title: s.title, ytid: s.youtubeVideoId };
  if (s.reviewStatus === "PENDING") return { ...base, status: "pending" };
  if (s.reviewStatus === "APPROVED" && s.guideId)
    return { ...base, status: "approved", guideId: s.guideId };
  return null;
}
