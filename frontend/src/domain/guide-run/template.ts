import type { GuideStepInfo } from "@/domain/session";
import type { AreaSubStep, TemplateId } from "@/vision/guide";

/** 코·콧·노즈가 든 단계 이름. 코렉터·코랄은 코가 아니다. AI가 쉐딩 단계를 코로 고르는 규칙과 같다 */
const NOSE = /콧|코(?!렉터|랄)|노즈/;

/** 쉐딩 단계 이름에 코가 있으면 얼굴 외곽 대신 코 쉐딩 기본 가이드를 쓴다 */
export function templateFor(id: TemplateId | null, label: string): TemplateId | null {
  return id === "contour" && NOSE.test(label) ? "contourNose" : id;
}

/**
 * 영역 데이터에 없는 단계는 화장 종류의 기본 가이드로 그린다.
 * 영역 데이터가 있는 단계는 AI가 하위 단계마다 기본 가이드 키(contourNose 포함)를 정해 보내므로 바꾸지 않는다
 */
export function templateOf(info: Pick<GuideStepInfo, "stepId" | "makeup" | "short">): AreaSubStep {
  return {
    subStepId: `${info.stepId}-1`,
    order: 1,
    status: "template",
    reasons: [],
    templateId: templateFor(info.makeup, info.short),
    guideSets: [],
  };
}
