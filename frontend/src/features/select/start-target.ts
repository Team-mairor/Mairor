import type { AnalysisJobReceipt, VideoSelection } from "@/lib/api";

/** 고른 영상을 어디서 시작할지. guide는 승인 가이드로 바로 따라 하기, job은 그 분석 작업의 로딩 화면 */
export type StartTarget = { kind: "guide"; guideId: string } | { kind: "job"; jobId: string };

/**
 * 선택 응답(API-VIDEO-001)만으로 정해지는 시작 지점. 승인 가이드가 먼저고, 다음은 내가 요청해 진행 중인 분석이다.
 * 둘 다 없으면 null이고 분석을 요청해야 한다
 */
export function targetOfSelection(s: VideoSelection): StartTarget | null {
  if (s.guideAvailable && s.guideId) return { kind: "guide", guideId: s.guideId };
  if (s.analysisJobId) return { kind: "job", jobId: s.analysisJobId };
  return null;
}

/** 분석 요청 영수증(API-VIDEO-002)의 시작 지점. REUSED_GUIDE면 가이드, 나머지는 작업. 받은 ID가 비면 null */
export function targetOfReceipt(r: AnalysisJobReceipt): StartTarget | null {
  if (r.receiptType === "REUSED_GUIDE")
    return r.guideId ? { kind: "guide", guideId: r.guideId } : null;
  return r.jobId ? { kind: "job", jobId: r.jobId } : null;
}
