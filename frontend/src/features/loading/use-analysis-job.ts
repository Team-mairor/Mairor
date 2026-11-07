import { useEffect, useState } from "react";

import { api, ApiError, apiUrl, isAbortError, type AnalysisJobStatus } from "@/lib/api";

import { isJobSettled, jobPercent } from "./analysis-job";

const RETRY_MS = 5000;

/**
 * 분석 작업 상태를 SSE(API-VIDEO-008)로 받는다. jobId가 없으면 아무것도 하지 않는다.
 * 연결이 닫히면(401·404·SSE를 못 쓰는 프록시) 상태 조회(API-VIDEO-003)로 원인을 보고, 되면 pollAfterSeconds마다 조회한다.
 * error는 다시 해도 소용없는 401 UNAUTHORIZED·404 NOT_FOUND만 담는다.
 */
export function useAnalysisJob(jobId: string | null) {
  const [job, setJob] = useState<AnalysisJobStatus | null>(null);
  const [pct, setPct] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const path = `/v1/users/me/analysis-jobs/${encodeURIComponent(jobId)}`;
    const ctrl = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const show = (j: AnalysisJobStatus) => {
      setJob(j);
      setPct((p) => Math.max(p, jobPercent(j)));
    };

    const poll = async () => {
      try {
        const j = await api.get<AnalysisJobStatus>(path, { signal: ctrl.signal });
        if (ctrl.signal.aborted) return;
        show(j);
        if (j.pollAfterSeconds !== null) timer = setTimeout(poll, j.pollAfterSeconds * 1000);
      } catch (e) {
        if (isAbortError(e) || ctrl.signal.aborted) return;
        if (e instanceof ApiError && (e.code === "UNAUTHORIZED" || e.code === "NOT_FOUND")) {
          setError(e);
          return;
        }
        // ponytail: 네트워크·5xx는 5초마다 끝없이 다시 조회한다. 오래 끊길 때 안내가 필요하면 횟수를 센다
        timer = setTimeout(poll, RETRY_MS);
      }
    };

    // 서버가 닫아도 EventSource는 다시 붙으므로, 더 받을 것이 없으면 직접 닫는다
    const es = new EventSource(apiUrl(`${path}/events`));
    es.addEventListener("status", (e) => {
      const j = JSON.parse((e as MessageEvent<string>).data) as AnalysisJobStatus;
      show(j);
      if (isJobSettled(j)) es.close();
    });
    // 일시적인 끊김은 CONNECTING으로 알아서 다시 붙는다. 200이 아닌 응답에서만 CLOSED가 된다
    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) void poll();
    };

    return () => {
      es.close();
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [jobId]);

  return { job, pct, error };
}
