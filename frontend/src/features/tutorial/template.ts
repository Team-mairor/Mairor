import type { AreaSubStep } from "@/features/guide";
import type { GuideStepInfo } from "@/features/session";

/** 영역 데이터에 없는 단계는 화장 종류의 기본 가이드로 그린다 */
export function templateOf(info: Pick<GuideStepInfo, "stepId" | "makeup">): AreaSubStep {
  return {
    subStepId: `${info.stepId}-1`,
    order: 1,
    status: "template",
    reasons: [],
    templateId: info.makeup,
    guideSets: [],
  };
}
