import type { AreaSubStep, GuideSet, GuideStep } from "./types";

/**
 * 하위 단계를 얼굴 위에 그릴 가이드로 바꾼다. 그릴 것이 없으면(notApplicable · failed) null.
 * template은 기본 가이드에서 templateId(화장 종류) 단계를 꺼내 쓴다.
 * stepId는 하위 단계 ID로 바꿔, 하위 단계가 바뀔 때 이전 영역의 표시 판정을 이어 쓰지 않게 한다.
 */
export function resolveSubStep(sub: AreaSubStep, defaults: GuideSet | null): GuideStep | null {
  switch (sub.status) {
    case "extracted":
      if (sub.guideSets.length === 0) return null;
      return {
        stepId: sub.subStepId,
        order: sub.order,
        title: "",
        regions: [...new Set(sub.guideSets.map((set) => set.region))],
        // 빼는 부위는 그 부위별 묶음의 도형에만 붙인다
        guides: sub.guideSets.flatMap((set) =>
          set.guides.map((g) => (set.exclude?.length ? { ...g, exclude: set.exclude } : g)),
        ),
        source: sub.guideSets.every((set) => set.source === "manual") ? "manual" : "extracted",
      };
    case "template": {
      const step = defaults?.steps.find((s) => s.stepId === sub.templateId);
      return step ? { ...step, stepId: sub.subStepId, order: sub.order } : null;
    }
    case "notApplicable":
    case "failed":
      return null;
  }
}
