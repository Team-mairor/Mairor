"use client";

import {
  api,
  type AnalysisJobReceipt,
  type PopularVideoResponse,
  type VideoSearchPage,
  type VideoSelection,
  type VideoSelectionRequest,
} from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";

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

/** GET /v1/videos/popular (API-VIDEO-005). 기록이 없으면 503 VIDEO_POPULAR_UNAVAILABLE */
function popularVideos(_key: string, signal: AbortSignal) {
  return api.get<PopularVideoResponse>("/v1/videos/popular", { signal });
}

/**
 * POST /v1/users/me/analysis-jobs (API-VIDEO-002). 선택 응답(또는 인기 영상)의 내부 videoId로 분석을 요청한다.
 * 승인 가이드가 있으면 200 REUSED_GUIDE(guideId), 진행 중 작업이 있으면 202 JOINED_JOB, 없으면 202 NEW_JOB(jobId)
 */
export function requestAnalysis(videoId: string) {
  return api.post<AnalysisJobReceipt>("/v1/users/me/analysis-jobs", { body: { videoId } });
}

export const useVideoSearch = (q: string) => useLoad(q, searchVideos);

export const useVideoSelection = (youtubeVideoId: string | null) =>
  useLoad(youtubeVideoId, selectVideo);

export const usePopularVideos = () => useLoad("popular", popularVideos);
