import { ANALYSIS_PHASES } from "@/domain/video";
import type { ApiError, AnalysisJobStatus } from "@/lib/api";

import { jobFailure, stageText } from "./analysis-job";
import { partLabel } from "./loading-labels";

const PHASE_EN = ["Queued", "Fetching", "Scenes", "Detecting", "Steps", "Composing"];

/** 실제 작업 FAILED와 조회할 수 없는 작업 */
export type Fail = null | "stopped" | "missing";
export type Review = null | "pending" | "rejected";

/** 로그인 만료(401)가 아닌 오류는 열 수 없는 작업으로 본다 */
export function jobFail(error: ApiError | null, job: AnalysisJobStatus | null): Fail {
  if (error && error.code !== "UNAUTHORIZED") return "missing";
  if (job?.status === "FAILED") return "stopped";
  return null;
}

export interface LoadingNotice {
  tag: string;
  title: string;
  sub: string;
  /** 서버가 다시 시도를 받아 줄 수 있다 */
  retry: boolean;
}

/** 분석 진행 상태와 안내 문구. 화면이 그릴 값을 한꺼번에 정한다 */
export function describeLoading(i: {
  pct: number;
  job: AnalysisJobStatus | null;
  activeJobId: string | null;
  /** 분석 없이 이미 있는 가이드로 시작한다 */
  replay: boolean;
  fail: Fail;
  review: Review;
  approvedGuide: string | null;
  retryRefused: boolean;
  /** 이 작업으로 고른 영상을 안다 */
  hasPicked: boolean;
  guideMode: boolean;
  guideReady: boolean;
}) {
  const { pct, job, activeJobId, replay, fail, review, approvedGuide } = i;
  const done = pct >= 100;
  const phaseIdx = done ? 6 : ANALYSIS_PHASES.filter((p) => pct >= p[2]).length - 1;
  const pi = Math.max(0, Math.min(5, phaseIdx));
  const phaseName = ANALYSIS_PHASES[pi][1];
  const phaseLabel = fail
    ? fail === "missing"
      ? "작업을 찾지 못했어요"
      : `${phaseName} 단계에서 멈췄어요`
    : done
      ? review === "pending"
        ? "분석 완료 · 검수 대기"
        : review === "rejected"
          ? "이용할 수 없음"
          : "분석이 끝났어요"
      : activeJobId
        ? (stageText(job?.stageProgress ?? null) ?? phaseName)
        : replay
          ? "분석이 끝났어요"
          : "가이드 준비";
  const phaseEn = fail ? "Stopped." : done ? (review ? "In review." : "Ready.") : PHASE_EN[pi];
  // 실제 작업은 남은 시간을 받지 못한다(estimatedRemainingSeconds가 늘 null)
  const eta = fail ? "멈춤" : done ? "완료" : activeJobId ? "처리 중" : "준비 완료";
  const scanSec = Math.floor(pct * 7.5);
  const scanTime = `${Math.floor(scanSec / 60)}:${String(scanSec % 60).padStart(2, "0")}`;
  const scanStatus = fail
    ? `STOPPED · ${scanTime}`
    : done
      ? review
        ? "IN REVIEW"
        : "ANALYSIS COMPLETE"
      : `SCANNING · ${scanTime}`;

  // 실제 작업은 상태 응답의 단계별 제품 결과를 표시한다
  const rows = (job?.foundProducts ?? []).map((product, i) => ({
    id: `${product.stepId ?? "product"}-${i}`,
    cat: partLabel(product.part),
    color: "#EADDE0",
    found: true,
    next: false,
    have: product.ownership === "OWNED",
    name: product.referenceProduct.name,
    productName: product.referenceProduct.name,
  }));
  const foundCount = rows.filter((r) => r.found).length;
  const haveCount = rows.filter((r) => r.have).length;

  const notice: LoadingNotice | null = fail
    ? {
        stopped: job
          ? jobFailure(i.retryRefused ? { ...job, retryable: false } : job, phaseName)
          : {
              tag: "STOPPED",
              title: "분석을 마치지 못했어요",
              sub: `${phaseName} 단계에서 멈췄어요. 다른 영상을 골라 주세요.`,
              retry: false,
            },
        missing: {
          tag: "NOT FOUND",
          title: "분석 작업을 찾을 수 없어요",
          sub: "주소를 다시 확인하거나 다른 영상을 골라 주세요.",
          retry: false,
        },
      }[fail]
    : review === "pending"
      ? {
          tag: "IN REVIEW",
          title: "분석은 끝났고, 검수 중이에요",
          // 고른 영상을 모르면 홈 카드를 만들 수 없어 홈 안내를 뺀다
          sub: i.hasPicked
            ? "검수를 통과한 가이드만 따라 할 수 있어요. 검수가 끝나면 홈에서 바로 시작할 수 있어요."
            : "검수를 통과한 가이드만 따라 할 수 있어요.",
          retry: false,
        }
      : review === "rejected"
        ? {
            tag: "REJECTED",
            title: "이 영상은 가이드로 쓸 수 없어요",
            sub: "이 영상의 가이드는 내려졌어요. 다른 영상을 골라 주세요.",
            retry: false,
          }
        : approvedGuide
          ? {
              tag: "READY",
              title: "분석이 끝났어요",
              sub: "이 영상의 가이드로 바로 따라 할 수 있어요.",
              retry: false,
            }
          : null;

  const guideOk = approvedGuide ? true : i.guideMode ? i.guideReady : replay || (done && !notice);
  const guideState = fail
    ? "멈춤"
    : review
      ? review === "pending"
        ? "검수 대기"
        : "이용 불가"
      : approvedGuide
        ? "준비 완료"
        : guideOk
          ? "완료"
          : `분석 중 ${pct}%`;

  return {
    done,
    phaseIdx,
    phaseEn,
    phaseLabel,
    phaseName,
    eta,
    scanStatus,
    rows,
    foundCount,
    haveCount,
    notice,
    guideOk,
    guideState,
  };
}

export type CtaAction = "guide" | "home" | "select" | "face" | "save-face" | "check";

/** 하단 큰 버튼의 글자와 눌렀을 때 동작. action이 없으면 누를 수 없다 */
export function loadingCta(i: {
  approvedGuide: string | null;
  review: Review;
  guideOk: boolean;
  faceCaptured: boolean;
  faceOk: boolean;
  guideMode: boolean;
  savingFace: boolean;
  faceSaveError: string | null;
}): { label: string; action: CtaAction | null } {
  if (i.approvedGuide) return { label: "가이드로 따라 하기", action: "guide" };
  if (i.review === "pending") return { label: "홈으로", action: "home" };
  if (i.review === "rejected") return { label: "다른 영상 고르기", action: "select" };
  if (!i.guideOk) return { label: "분석이 끝나면 제품을 확인할 수 있어요", action: null };
  if (!i.faceCaptured) return { label: "얼굴 등록하고 제품 확인", action: "face" };
  if (!i.faceOk && i.guideMode) {
    return {
      label: i.savingFace
        ? "얼굴 등록을 저장하는 중"
        : i.faceSaveError
          ? "얼굴 등록 저장 다시 시도"
          : "제품 확인하기",
      action: i.savingFace ? null : "save-face",
    };
  }
  return { label: "제품 확인하기", action: "check" };
}
