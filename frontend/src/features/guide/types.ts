import type { GuideShape, RegionName } from "@/features/face";

/** 가이드 도형. exclude는 영역(polygon)에서 빼고 그릴 부위로, 아이섀도의 눈처럼 바르면 안 되는 곳이다 */
export type GuideItem = GuideShape & { exclude?: RegionName[]; region?: RegionName };

/** 튜토리얼 한 단계의 가이드 */
export interface GuideStep {
  stepId: string;
  /** 1부터 */
  order: number;
  /** 화면에 띄우는 안내 문구 */
  title: string;
  /** 이 단계가 다루는 부위. 부위가 화면 밖이거나 돌아가 있으면 가이드를 숨긴다 */
  regions: RegionName[];
  guides: GuideItem[];
  /** extracted: 분석 결과, template: 기본 템플릿, manual: 사람이 고침. 화면에서 추정 여부를 알릴 때 쓴다 */
  source: "extracted" | "template" | "manual";
}

/** 기본 가이드와 확인용 가이드 파일의 형식 */
export interface GuideSet {
  meshVersion: "v1";
  steps: GuideStep[];
}

/** 화장 종류. 기본 가이드 키와 같다 */
export type Makeup =
  | "foundation"
  | "eyeshadow"
  | "eyeliner"
  | "blush"
  | "lip"
  | "brow"
  | "mascara"
  | "contour"
  | "highlight"
  | "other";

/**
 * 기본 가이드 키. 눈 화장은 바른 자리별 템플릿을 더 쓴다.
 * contourNose는 FE에서만 쓴다. 쉐딩 단계 이름에 코가 있으면 contour 대신 고른다
 */
export type TemplateId =
  | Makeup
  | "eyeshadowUpper"
  | "eyeshadowUnder"
  | "eyelinerWaterline"
  | "eyelinerUnder"
  | "contourNose";

/**
 * AI가 넘기는 영상 하나의 단계별 도포 영역 (shared/guide-area).
 * 단계 → 하위 단계 → 부위별 묶음 → 도형 순서다
 */
export interface GuideArea {
  videoId: string;
  meshVersion: "v1";
  steps: AreaStep[];
}

export interface AreaStep {
  stepId: string;
  order: number;
  makeup: Makeup;
  subSteps: AreaSubStep[];
}

/**
 * extracted: 영상에서 찾은 영역 / template: 못 찾아 기본 가이드로 대신 /
 * notApplicable: 영역이 없는 단계 / failed: 못 찾았고 기본 가이드도 쓰지 않음
 */
export type AreaStatus = "extracted" | "template" | "notApplicable" | "failed";

export interface AreaSubStep {
  subStepId: string;
  order: number;
  status: AreaStatus;
  reasons: string[];
  templateId: TemplateId | null;
  guideSets: AreaGuideSet[];
}

export interface AreaGuideSet {
  region: RegionName;
  source: "extracted" | "manual";
  /** 찾은 도포 영역과, 바르기 시작한 곳에서 진행 방향으로 향하는 화살표 */
  guides: Extract<GuideShape, { type: "polygon" | "arrow" }>[];
  exclude?: RegionName[];
}
