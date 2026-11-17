"use client";

import { useCallback, useEffect, useState } from "react";

import { ANALYSIS_PHASES } from "@/domain/video";
import {
  api,
  ApiError,
  apiUrl,
  isAbortError,
  type AnalysisJobStatus,
  type StageProgress,
} from "@/lib/api";

/** progressStage → ANALYSIS_PHASES 칸 번호 */
const STAGE_INDEX: Record<AnalysisJobStatus["progressStage"], number> = {
  QUEUED: 0,
  LOADING_VIDEO: 1,
  SEGMENTING: 2,
  RECOGNIZING_PRODUCTS: 3,
  EXTRACTING_STEPS: 4,
  BUILDING_GUIDE: 5,
  DONE: 6,
};

/** 가이드 구성 단계 안에서 숫자가 오는 순서. 단계 구간을 넷으로 나눠 채운다 */
const ITEMS: StageProgress["item"][] = ["FRAMES", "LANDMARKS", "AREA", "EXPLANATION"];

const ITEM_TEXT: Record<StageProgress["item"], [label: string, unit: string]> = {
  FRAMES: ["사진 받는 중", "장"],
  LANDMARKS: ["얼굴 분석", "장"],
  AREA: ["가이드 영역 만드는 중", "단계"],
  EXPLANATION: ["쉬운 설명 만드는 중", "단계"],
};

/**
 * 전체 추정 %. BE가 전체 %를 주지 않아 단계 구간과 단계 안 숫자로 어림한다. 끝나기 전에는 99를 넘지 않는다.
 * ponytail: 임시 계산. BE가 progressPercent를 주면 그 값으로 바꾼다
 */
export function jobPercent(job: AnalysisJobStatus) {
  if (job.status === "COMPLETED") return 100;
  // 모르는 단계(BE가 단계를 늘린 경우 등)는 처음 단계로 본다
  const i = Math.min(STAGE_INDEX[job.progressStage] ?? 0, ANALYSIS_PHASES.length - 1);
  const from = ANALYSIS_PHASES[i][2];
  const to = ANALYSIS_PHASES[i + 1]?.[2] ?? 100;
  const p = job.stageProgress;
  const k = p ? ITEMS.indexOf(p.item) : -1;
  const inside =
    p && k >= 0 && p.total > 0 ? (k + Math.min(1, p.done / p.total)) / ITEMS.length : 0;
  return Math.min(99, Math.floor(from + (to - from) * inside));
}

/** "얼굴 분석 840 / 2,000장". 단계 안 숫자가 없으면 null */
export function stageText(p: StageProgress | null) {
  // 모르는 item(BE가 늘린 경우 등)은 단계 이름만 보여 준다
  if (!p || !(p.item in ITEM_TEXT)) return null;
  const [label, unit] = ITEM_TEXT[p.item];
  return `${label} ${p.done.toLocaleString("ko-KR")} / ${p.total.toLocaleString("ko-KR")}${unit}`;
}

/** 더 바뀌지 않는 상태(실패·승인·반려). BE AnalysisJobStatusView.isFinal과 같다. 검수 대기는 승인·반려를 계속 받는다 */
export function isJobSettled(job: AnalysisJobStatus) {
  return (
    job.status === "FAILED" || job.reviewStatus === "APPROVED" || job.reviewStatus === "REJECTED"
  );
}

/** 로딩 화면의 검수 표시. 분석이 끝났는데 승인 전이면 검수 대기로 본다 */
export function jobReview(job: AnalysisJobStatus) {
  if (job.reviewStatus === "REJECTED") return "rejected";
  if (job.status === "COMPLETED" && job.reviewStatus !== "APPROVED") return "pending";
  return null;
}

/** 실패 코드별 제목. 없으면 기본 문구. failureMessage는 운영자용이라 보여 주지 않는다 */
const FAILURE_TITLE: Record<string, string> = {
  NO_VALID_STEPS: "따라 할 수 있는 단계를 찾지 못했어요",
  VIDEO_DOWNLOAD_REJECTED: "이 영상은 받을 수 없어요",
  SOURCE_NOT_FOUND: "이 영상은 받을 수 없어요",
  SOURCE_UNREADABLE: "이 영상은 받을 수 없어요",
  PROCESSOR_TIMEOUT: "분석이 너무 오래 걸려 멈췄어요",
  ANALYSIS_TIMEOUT: "분석이 너무 오래 걸려 멈췄어요",
};
const TIMEOUTS = new Set(["PROCESSOR_TIMEOUT", "ANALYSIS_TIMEOUT"]);

/** 실제 작업 실패 안내. retryable이면 다시 시도할 수 있다(재시도 불가 실패 · 시도 횟수를 다 쓴 작업은 false) */
export function jobFailure(job: AnalysisJobStatus, phaseName: string) {
  const code = job.failureCode ?? "";
  return {
    tag: TIMEOUTS.has(code) ? "STOPPED · TIMEOUT" : "STOPPED",
    title: FAILURE_TITLE[code] ?? "분석을 마치지 못했어요",
    sub: job.retryable
      ? `${phaseName} 단계에서 멈췄어요. 잠깐의 문제일 수 있어요. 다시 시도해 보세요.`
      : `${phaseName} 단계에서 멈췄어요. 다른 영상을 골라 주세요.`,
    retry: job.retryable,
  };
}

/** 분석 재시도. 받은 상태의 jobId가 다르면 같은 영상의 다른 진행 중 작업에 합류한 것이다 */
export function retryAnalysisJob(jobId: string) {
  return api.post<AnalysisJobStatus>(
    `/v1/users/me/analysis-jobs/${encodeURIComponent(jobId)}/retry`,
  );
}

const RETRY_MS = 5000;
/** SSE 다시 붙기가 이만큼 연달아 실패하면 상태 조회로 바꾼다 */
const SSE_MAX_FAILS = 3;

/**
 * 분석 작업 상태를 SSE(API-VIDEO-008)로 받고, SSE가 안 되면 상태 조회(API-VIDEO-003)를 pollAfterSeconds마다 부른다.
 * error는 다시 해도 소용없는 4xx만 담는다(408·429는 다시 조회).
 * restart는 같은 작업을 재시도한 뒤 받은 상태로 바꾸고 진행률을 되돌려 다시 받기 시작한다(진행률은 평소 줄지 않는다).
 */
export function useAnalysisJob(jobId: string | null) {
  const [job, setJob] = useState<AnalysisJobStatus | null>(null);
  const [pct, setPct] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [round, setRound] = useState(0);

  const restart = useCallback((next: AnalysisJobStatus) => {
    setJob(next);
    setPct(jobPercent(next));
    setError(null);
    setRound((r) => r + 1);
  }, []);

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
        if (j.pollAfterSeconds !== null && !isJobSettled(j)) {
          timer = setTimeout(poll, j.pollAfterSeconds * 1000);
        }
      } catch (e) {
        if (isAbortError(e) || ctrl.signal.aborted) return;
        if (
          e instanceof ApiError &&
          e.status >= 400 &&
          e.status < 500 &&
          ![408, 429].includes(e.status)
        ) {
          setError(e);
          return;
        }
        // ponytail: 네트워크·5xx는 5초마다 끝없이 다시 조회한다. 오래 끊길 때 안내가 필요하면 횟수를 센다
        timer = setTimeout(poll, RETRY_MS);
      }
    };

    // 서버가 닫아도 EventSource는 다시 붙으므로, 더 받을 것이 없으면 직접 닫는다
    const es = new EventSource(apiUrl(`${path}/events`));
    let fails = 0;
    es.addEventListener("status", (e) => {
      fails = 0;
      let j: AnalysisJobStatus;
      try {
        j = JSON.parse((e as MessageEvent<string>).data) as AnalysisJobStatus;
      } catch {
        return; // 깨진 이벤트 하나는 건너뛰고 다음 이벤트를 기다린다
      }
      show(j);
      if (isJobSettled(j)) es.close();
    });
    // 200이 아닌 응답은 CLOSED, 네트워크 오류는 CONNECTING으로 다시 붙는다. 다시 붙기가 거듭 실패해도 상태 조회로 바꾼다
    es.onerror = () => {
      if (es.readyState !== EventSource.CLOSED && ++fails < SSE_MAX_FAILS) return;
      es.close();
      void poll();
    };

    return () => {
      es.close();
      ctrl.abort();
      clearTimeout(timer);
    };
  }, [jobId, round]);

  return { job, pct, error, restart };
}
