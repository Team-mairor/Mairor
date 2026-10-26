import type { GuideShape, RegionName } from "@/features/face";

/** 튜토리얼 한 단계의 가이드 */
export interface GuideStep {
  stepId: string;
  /** 1부터 */
  order: number;
  /** 화면에 띄우는 안내 문구 */
  title: string;
  /** 이 단계가 다루는 부위. 부위가 화면 밖이거나 돌아가 있으면 가이드를 숨긴다 */
  regions: RegionName[];
  guides: GuideShape[];
  /** extracted: 분석 결과, template: 기본 템플릿, manual: 사람이 고침. 화면에서 추정 여부를 알릴 때 쓴다 */
  source: "extracted" | "template" | "manual";
}

export interface GuideSet {
  meshVersion: "v1";
  steps: GuideStep[];
}
