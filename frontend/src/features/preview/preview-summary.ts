import type { StepMatch } from "@/features/check/match-api";
import { MAKEUP_LABEL, type GuideModel } from "@/features/guide";

export interface PreviewSummary {
  targets: number;
  total: number;
  /** 미리보기 대상 화장 종류 이름. 단계 순서, 중복 없음 */
  kinds: string[];
  /** 대상 단계가 하나도 없는 화장 종류 이름 */
  excluded: string[];
}

export interface PreviewMatchGroups {
  owned: GuideModel["steps"];
  substitutes: GuideModel["steps"];
  none: GuideModel["steps"];
  unresolved: GuideModel["steps"];
}

const kindsOf = (steps: GuideModel["steps"]) => [
  ...new Set(steps.map((s) => MAKEUP_LABEL[s.makeup])),
];

export function previewSummary(guide: GuideModel): PreviewSummary {
  const targets = guide.steps.filter((s) => s.previewable);
  const kinds = kindsOf(targets);
  return {
    targets: targets.length,
    total: guide.steps.length,
    kinds,
    excluded: kindsOf(guide.steps.filter((s) => !s.previewable)).filter((k) => !kinds.includes(k)),
  };
}

/** 미리보기 대상 단계를 서버 매칭 판정으로 나눈다. 응답이 없는 단계는 후보 없음으로 오분류하지 않는다. */
export function previewMatchGroups(
  guide: GuideModel,
  matches: Map<string, StepMatch>,
): PreviewMatchGroups {
  const groups: PreviewMatchGroups = { owned: [], substitutes: [], none: [], unresolved: [] };
  for (const step of guide.steps) {
    if (!step.previewable) continue;
    const match = matches.get(step.stepId);
    if (!match) groups.unresolved.push(step);
    else if (match.result === "SAME") groups.owned.push(step);
    else if (match.result === "SUBSTITUTE") groups.substitutes.push(step);
    else groups.none.push(step);
  }
  return groups;
}
