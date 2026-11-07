import { ANALYSIS_PHASES } from "@/features/video";
import type { AnalysisJobStatus, StageProgress } from "@/lib/api";

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
 * 화면에 보일 전체 추정 %. BE는 전체 %를 주지 않아(가중치 실측 전) 단계 구간(ANALYSIS_PHASES)과
 * 단계 안 숫자로 어림한다. 끝나기 전에는 99를 넘지 않고, 줄어들지 않게 하는 것은 부르는 쪽이 맡는다.
 */
export function jobPercent(job: AnalysisJobStatus) {
  if (job.status === "COMPLETED") return 100;
  const i = Math.min(STAGE_INDEX[job.progressStage], ANALYSIS_PHASES.length - 1);
  const from = ANALYSIS_PHASES[i][2];
  const to = ANALYSIS_PHASES[i + 1]?.[2] ?? 100;
  const p = job.stageProgress;
  const inside =
    p && p.total > 0 ? (ITEMS.indexOf(p.item) + Math.min(1, p.done / p.total)) / ITEMS.length : 0;
  return Math.min(99, Math.floor(from + (to - from) * inside));
}

/** "얼굴 분석 840 / 2,000장". 단계 안 숫자가 없으면 null */
export function stageText(p: StageProgress | null) {
  if (!p) return null;
  const [label, unit] = ITEM_TEXT[p.item];
  return `${label} ${p.done.toLocaleString("ko-KR")} / ${p.total.toLocaleString("ko-KR")}${unit}`;
}

/** 더 기다릴 것이 없는 상태. 실패·승인·반려와 검수 대기(홈 카드로 간다)에서 SSE를 닫는다 */
export function isJobSettled(job: AnalysisJobStatus) {
  return (
    job.status === "FAILED" ||
    job.reviewStatus === "APPROVED" ||
    job.reviewStatus === "REJECTED" ||
    (job.status === "COMPLETED" && job.reviewStatus === "PENDING")
  );
}

/** 로딩 화면의 검수 표시. 분석이 끝났는데 승인 전이면 검수 대기로 본다 */
export function jobReview(job: AnalysisJobStatus) {
  if (job.reviewStatus === "REJECTED") return "rejected";
  if (job.status === "COMPLETED" && job.reviewStatus !== "APPROVED") return "pending";
  return null;
}
