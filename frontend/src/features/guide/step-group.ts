import type { MatchCategory } from "./guide-model";
import type { Makeup } from "./types";

/** 화장 종류 → 매칭 카테고리. 서버가 matchCategory를 정하는 규칙과 같고, 기타는 카테고리가 없다 */
export const MAKEUP_CATEGORY: Record<Makeup, MatchCategory | null> = {
  foundation: "BASE",
  eyeshadow: "EYE",
  eyeliner: "EYE",
  mascara: "EYE",
  brow: "BROW",
  blush: "CHEEK",
  highlight: "CHEEK",
  contour: "CHEEK",
  lip: "LIP",
  other: null,
};

export const CATEGORY_LABEL: Record<MatchCategory, string> = {
  BASE: "피부",
  EYE: "눈",
  BROW: "눈썹",
  CHEEK: "볼",
  LIP: "입술",
};

/** 화장 종류 이름(part)으로 카테고리를 찾는다. 모르는 이름이면 null */
export function categoryOfPart(part: string): MatchCategory | null {
  return Object.hasOwn(MAKEUP_CATEGORY, part) ? MAKEUP_CATEGORY[part as Makeup] : null;
}

/** 연속한 같은 묶음 키 단계 묶음. 부위 이름은 첫 단계 카테고리로 정한다. end는 묶음 다음 단계의 순번이다 */
export interface StepGroup {
  category: MatchCategory | null;
  label: string;
  start: number;
  end: number;
}

type GroupedStep = { category: MatchCategory | null; title: string };

/**
 * 영상 순서를 바꾸지 않고 연속한 같은 묶음 키 단계만 묶는다. 키를 주지 않으면 카테고리로 묶는다.
 * 키가 없는 단계는 하나씩 따로 두고, 카테고리를 모르는 묶음은 단계 이름을 묶음 이름으로 쓴다.
 */
export function groupSteps<S extends GroupedStep>(
  steps: readonly S[],
  keyOf: (s: S) => string | null = (s) => s.category,
): StepGroup[] {
  const groups: StepGroup[] = [];
  let prevKey: string | null = null;
  steps.forEach((s, i) => {
    const key = keyOf(s);
    const prev = groups.at(-1);
    if (prev && key !== null && key === prevKey) prev.end = i + 1;
    else
      groups.push({
        category: s.category,
        label: s.category ? CATEGORY_LABEL[s.category] : s.title,
        start: i,
        end: i + 1,
      });
    prevKey = key;
  });
  return groups;
}

/** step이 들어 있는 묶음의 순번. 범위 밖이면 -1 */
export const groupIndexOf = (groups: readonly StepGroup[], step: number) =>
  groups.findIndex((g) => step >= g.start && step < g.end);
