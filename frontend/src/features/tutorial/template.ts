import type { AreaSubStep, TemplateId } from "@/features/guide";
import type { GuideStepInfo } from "@/features/session";

/** 쉐딩 단계 이름에 코가 있으면 얼굴 외곽 대신 코 쉐딩 기본 가이드를 쓴다 */
export function templateFor(id: TemplateId | null, label: string): TemplateId | null {
  return id === "contour" && /코|콧/.test(label) ? "contourNose" : id;
}

/** 영역 데이터에 없는 단계는 화장 종류의 기본 가이드로 그린다 */
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

/** 기본 가이드를 쓰는 하위 단계는 단계 이름에 맞는 기본 가이드로 바꾼다 */
export function withStepTemplate(subs: AreaSubStep[], label: string): AreaSubStep[] {
  return subs.map((sub) =>
    sub.status === "template" ? { ...sub, templateId: templateFor(sub.templateId, label) } : sub,
  );
}
