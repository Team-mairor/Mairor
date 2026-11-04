import type { AreaSubStep, GuideSet, GuideStep, TemplateId } from "./types";

/** eyeshadow(위아래)에 이미 들어 있는 바른 자리별 템플릿 */
const EYESHADOW_PARTS = new Set<TemplateId | null>(["eyeshadowUpper", "eyeshadowUnder"]);

/**
 * 하위 단계를 얼굴 위에 그릴 가이드로 바꾼다. 그릴 것이 없으면(notApplicable · failed) null.
 * template은 기본 가이드에서 templateId(기본 가이드 키) 단계를 꺼내 쓴다.
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
      if (!defaults) return null;
      const step = defaults.steps.find((s) => s.stepId === sub.templateId);
      if (!step) console.warn(`${sub.subStepId}의 기본 가이드 ${sub.templateId}가 없어 뺍니다`);
      return step ? { ...step, stepId: sub.subStepId, order: sub.order } : null;
    }
    case "notApplicable":
    case "failed":
      return null;
  }
}

/**
 * 한 단계의 하위 단계를 모두 합쳐 한 번에 그릴 가이드로 바꾼다. 그릴 것이 하나도 없으면 null.
 * 영상에서 뽑은 영역이 하나라도 있으면 기본 템플릿은 겹쳐 그리지 않고, 같은 템플릿은 한 번만 쓴다.
 * eyeshadow는 eyeshadowUpper·eyeshadowUnder를 포함하므로 함께 오면 둘은 뺀다.
 * 하위 단계 중 하나라도 기본 템플릿이면 source는 template이라 화면이 기본 위치를 썼다고 알린다.
 */
export function resolveStep(
  stepId: string,
  subs: AreaSubStep[],
  defaults: GuideSet | null,
): GuideStep | null {
  const extracted = subs.some((sub) => sub.status === "extracted" && sub.guideSets.length > 0);
  const eyeshadow = subs.some((sub) => sub.status === "template" && sub.templateId === "eyeshadow");
  const seen = new Set<string | null>();
  const used = subs.filter((sub) => {
    if (sub.status !== "template") return true;
    if (extracted || seen.has(sub.templateId)) return false;
    if (eyeshadow && EYESHADOW_PARTS.has(sub.templateId)) return false;
    seen.add(sub.templateId);
    return true;
  });
  const steps = used.flatMap((sub) => resolveSubStep(sub, defaults) ?? []);
  if (steps.length === 0) return null;
  return {
    stepId,
    order: steps[0].order,
    title: "",
    regions: [...new Set(steps.flatMap((s) => s.regions))],
    guides: steps.flatMap((s) => s.guides),
    source: steps.some((s) => s.source === "template")
      ? "template"
      : steps.every((s) => s.source === "manual")
        ? "manual"
        : "extracted",
  };
}
