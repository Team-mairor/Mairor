"use client";

import { fromSummary, useReports } from "@/domain/report";
import {
  isGuideId,
  useAuth,
  useMyPouch,
  usePendingGuide,
  usePouchSync,
  useSessionActions,
} from "@/domain/session";
import { toPendingGuide, useLatestAnalysis } from "@/features/loading";
import { useQuery } from "@/lib/hooks/use-query";

/** 홈이 보여 줄 서버 기록·파우치·검수 카드. 로그인 여부와 받는 상태에 따라 보여 줄 것을 정한다 */
export function useHomeData() {
  const { loggedIn, email } = useAuth();
  const { pouch: stored } = useMyPouch();
  const { pendingGuide } = usePendingGuide();
  const { sessionChecked } = useSessionActions();
  // 로그인했으면 파우치 보드를 서버 목록으로 맞춘다
  const sync = usePouchSync();
  const query = useQuery();
  // ?empty=1: 리포트·파우치 빈 상태 확인용 (데이터는 지우지 않는다)
  const empty = query?.get("empty") === "1";

  // 서버 기록은 로그인한 계정에서만 표시한다
  const myReports = useReports(sessionChecked && loggedIn ? email : null);
  const reports = empty
    ? []
    : loggedIn
      ? myReports.load.status === "ready"
        ? myReports.load.data.items.map(fromSummary)
        : []
      : [];
  // 서버 기록을 받는 중 · 받지 못했으면 빈 상태 대신 그대로 알린다
  const reportsWaiting =
    !empty && loggedIn && (!sessionChecked || myReports.load.status === "loading");
  const reportsError = !empty && loggedIn && myReports.load.status === "error";

  // 로그인했으면 서버 목록을 받기 전·받지 못했을 때 저장된(지난) 파우치를 보여 주지 않는다 (내 파우치와 같다)
  const pouchWaiting = sync.status === "loading" || (loggedIn && !sessionChecked);
  const pouchHidden = pouchWaiting || sync.status === "error";
  const pouch = empty || pouchHidden || !loggedIn ? [] : stored;

  // 로그인했으면 검수 카드는 내 분석 목록(API-VIDEO-007)의 가장 최근 것이다. 받기 전에는 띄우지 않고,
  // 비로그인이거나 목록을 받지 못하면 기기에 저장한 카드(샘플 흐름 · 개발 도구)를 쓴다
  const mine = useLatestAnalysis(sessionChecked && loggedIn ? email : null);
  const cardWaiting = loggedIn && (!sessionChecked || mine.load.status === "loading");
  const latest = mine.load.status === "ready" ? mine.load.data.items[0] : undefined;
  const pg =
    empty || cardWaiting
      ? null
      : mine.load.status === "ready"
        ? latest
          ? toPendingGuide(latest)
          : null
        : loggedIn
          ? pendingGuide
          : null;
  // 승인됐어도 guideId가 올바르지 않으면 시작하지 않고 다시 확인을 안내한다
  const ready = pg?.status === "approved" && isGuideId(pg.guideId);

  return {
    reports,
    reportsWaiting,
    reportsError,
    retryReports: myReports.retry,
    pouch,
    sync,
    pouchWaiting,
    pouchHidden,
    pg,
    ready,
  };
}
