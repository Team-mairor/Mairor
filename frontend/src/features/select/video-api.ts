"use client";

import { useEffect, useState } from "react";

import {
  api,
  isAbortError,
  type AnalysisJobReceipt,
  type VideoSearchPage,
  type VideoSelection,
  type VideoSelectionRequest,
} from "@/lib/api";

export type Load<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: unknown };

/** GET /v1/videos/search (API-VIDEO-004). 첫 페이지만 쓴다 */
function searchVideos(q: string, signal: AbortSignal) {
  return api.get<VideoSearchPage>("/v1/videos/search", { query: { q }, signal });
}

/** POST /v1/videos (API-VIDEO-001). 라이선스를 다시 확인하고 챕터·가이드 유무를 준다. 분석은 만들지 않는다 */
function selectVideo(youtubeVideoId: string, signal: AbortSignal) {
  return api.post<VideoSelection>("/v1/videos", {
    body: { youtubeVideoId } satisfies VideoSelectionRequest,
    signal,
  });
}

/**
 * POST /v1/users/me/analysis-jobs (API-VIDEO-002). 선택 응답의 내부 videoId로 분석을 요청한다.
 * 승인 가이드가 있으면 200 REUSED_GUIDE(guideId), 진행 중 작업이 있으면 202 JOINED_JOB, 없으면 202 NEW_JOB(jobId)
 */
export function requestAnalysis(videoId: string) {
  return api.post<AnalysisJobReceipt>("/v1/users/me/analysis-jobs", { body: { videoId } });
}

/**
 * key가 바뀔 때마다 다시 부른다. key가 바뀌거나 화면을 떠나면 이전 요청을 취소해 늦은 응답이 새 결과를 덮지 않는다.
 * key가 null이면 부르지 않는다(idle)
 */
function useLoad<T>(key: string | null, run: (key: string, signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<Load<T>>({ status: key ? "loading" : "idle" });

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- key가 바뀔 때만 상태를 다시 정한다 */
    if (!key) {
      setLoad({ status: "idle" });
      return;
    }
    setLoad({ status: "loading" });
    /* eslint-enable react-hooks/set-state-in-effect */
    const controller = new AbortController();
    run(key, controller.signal).then(
      (data) => setLoad({ status: "ready", data }),
      (error: unknown) => {
        if (!isAbortError(error)) setLoad({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [key, run, attempt]);

  return { load, retry: () => setAttempt((n) => n + 1) };
}

export const useVideoSearch = (q: string) => useLoad(q, searchVideos);

export const useVideoSelection = (youtubeVideoId: string | null) =>
  useLoad(youtubeVideoId, selectVideo);
