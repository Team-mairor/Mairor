"use client";

import { useEffect, useState } from "react";

import { ApiError, errorMessage, isAbortError } from "@/lib/api";

import { fetchGuide } from "./guide-api";
import { toGuideModel, type GuideModel } from "./guide-model";

export type GuideLoad =
  | { status: "loading" }
  | { status: "ready"; guide: GuideModel }
  /** 주소의 guideId가 UUID 형식이 아님 */
  | { status: "invalidId" }
  /** 없거나 검수 전·반려 (서버가 구분해 주지 않는다) */
  | { status: "notFound" }
  | { status: "login" }
  | { status: "error"; message: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * guideId의 가이드를 불러온다. guideId가 바뀌거나 화면을 떠나면 이전 요청을 취소해,
 * 늦게 온 이전 가이드 응답이 새 가이드를 덮지 않게 한다. retry를 부르면 다시 조회한다.
 */
export function useGuide(guideId: string): { load: GuideLoad; retry: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<GuideLoad>({ status: "loading" });

  useEffect(() => {
    // 주소에서 읽은 값이 바뀔 때만 상태를 다시 정한다
    /* eslint-disable react-hooks/set-state-in-effect */
    if (!UUID.test(guideId)) {
      setLoad({ status: "invalidId" });
      return;
    }
    setLoad({ status: "loading" });
    /* eslint-enable react-hooks/set-state-in-effect */
    const controller = new AbortController();
    fetchGuide(guideId, controller.signal)
      .then((raw) => setLoad({ status: "ready", guide: toGuideModel(raw, guideId) }))
      .catch((e: unknown) => {
        if (isAbortError(e)) return;
        if (e instanceof ApiError && e.status === 404) return setLoad({ status: "notFound" });
        if (e instanceof ApiError && e.status === 401) return setLoad({ status: "login" });
        console.warn("가이드를 불러오지 못했습니다", e);
        setLoad({
          status: "error",
          message: e instanceof ApiError ? errorMessage(e) : "가이드 내용을 읽지 못했어요.",
        });
      });
    return () => controller.abort();
  }, [guideId, attempt]);

  return { load, retry: () => setAttempt((n) => n + 1) };
}
