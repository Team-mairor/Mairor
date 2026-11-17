import { api } from "@/lib/api";
import type { AreaSubStep } from "@/vision/guide/types";

/** 단계 안의 동작 하나와 그 팁·주의 */
export interface GuideActionDto {
  text: string;
  tip: { kind: "tip" | "caution"; text: string } | null;
}

/** 영상에 나온 제품. 1차는 이름만 확인한 상태(UNMATCHED)라 제품·호수 ID가 없다 */
export interface ReferenceProductDto {
  productId: string | null;
  shadeId: string | null;
  /** 브랜드와 제품 이름 */
  name: string | null;
  shadeName: string | null;
  matchStatus: "MATCHED" | "CANDIDATE" | "UNMATCHED";
  verification: "CONFIRMED" | "ESTIMATED" | "UNKNOWN";
  sources: string[];
  videoConfirmed: boolean | null;
}

/** 가이드 단계. EXCLUDED는 스킨케어처럼 따라 하지 않는 단계다 */
export interface GuideStepDto {
  stepId: string;
  order: number;
  type: "GUIDE" | "EXCLUDED";
  /** 화장 종류 (foundation·eyeshadow·…·other) */
  part: string;
  /** 한국어 부위 이름 */
  partLabel: string | null;
  summary: string | null;
  actions: GuideActionDto[];
  doneWhen: string | null;
  tools: string[];
  referenceProduct: ReferenceProductDto | null;
  /** 목표 발색. 1차는 항상 null */
  targetColor: unknown;
  videoRange: { startSeconds: number; endSeconds: number };
  matchCategory: string | null;
  /** shared/guide-area의 하위 단계 그대로. 영역이 없으면 빈 목록 */
  subSteps: AreaSubStep[];
}

/** 검수 승인된 가이드 (GET /v1/guides/{guideId}) */
export interface GuideDto {
  guideId: string;
  guideVersion: number;
  videoId: string;
  youtubeVideoId: string;
  title: string;
  channelTitle: string;
  thumbnailUrl: string | null;
  /** 가이드 영역의 얼굴 메시 판. 영역이 없으면 null */
  meshVersion: string | null;
  referenceImageUrl: string | null;
  /** GUIDE 단계 수 */
  stepCount: number;
  /** order 순. GUIDE·EXCLUDED가 섞여 있다 */
  steps: GuideStepDto[];
}

/**
 * 승인된 가이드를 조회한다. 회원 세션이 필요하고, 없거나 검수 전·반려면 404다.
 * 응답은 검사하지 않은 채 돌려주므로 toGuideModel로 확인해서 쓴다.
 */
export function fetchGuide(guideId: string, signal?: AbortSignal) {
  return api.get<unknown>(`/v1/guides/${encodeURIComponent(guideId)}`, {
    signal,
    cache: "no-store",
  });
}
