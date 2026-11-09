import { MAKEUP_LABEL, type GuideModel } from "@/features/guide";

export interface PreviewSummary {
  targets: number;
  total: number;
  /** 미리보기 대상 화장 종류 이름. 단계 순서, 중복 없음 */
  kinds: string[];
  /** 대상 단계가 하나도 없는 화장 종류 이름 */
  excluded: string[];
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
