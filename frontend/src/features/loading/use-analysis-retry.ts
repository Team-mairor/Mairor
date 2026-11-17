"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useRun, useSessionActions } from "@/domain/session";
import { ApiError, errorMessage, type AnalysisJobStatus } from "@/lib/api";

import { retryAnalysisJob } from "./analysis-job";

/** 실패한 분석 작업을 다시 시도한다. 서버가 다시 시도할 수 없다고 하면 버튼을 거둔다 */
export function useAnalysisRetry({
  activeJobId,
  restart,
}: {
  activeJobId: string | null;
  /** 같은 작업으로 다시 시작됐을 때 상태 조회를 새로 시작한다 */
  restart: (next: AnalysisJobStatus) => void;
}) {
  const router = useRouter();
  const { run, updateRun } = useRun();
  const { expireSession } = useSessionActions();
  /** 요청 중 · 실패 문구 · 서버가 다시 시도할 수 없다고 한 작업 */
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refused, setRefused] = useState(false);

  const retry = async () => {
    if (!activeJobId || retrying) return;
    setRetrying(true);
    setError(null);
    try {
      const next = await retryAnalysisJob(activeJobId);
      if (next.jobId === activeJobId) {
        restart(next);
        return;
      }
      // 재시도 합류에도 촬영 상태를 유지한다.
      updateRun({ jobId: next.jobId }, run.id);
      router.replace(`/loading?jobId=${encodeURIComponent(next.jobId)}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "UNAUTHORIZED") {
        expireSession();
        router.replace("/login?expired=basic");
        return;
      }
      // 서버가 다시 시도할 수 없다고 하면 버튼을 거두고, 안내 문구가 이미 다른 영상을 권하므로 이유만 짧게
      if (e instanceof ApiError && e.code === "ANALYSIS_NOT_RETRYABLE") {
        setRefused(true);
        setError("이 분석은 다시 시도할 수 없어요.");
        return;
      }
      setError(errorMessage(e));
    } finally {
      setRetrying(false);
    }
  };

  return { retrying, error, refused, retry };
}
