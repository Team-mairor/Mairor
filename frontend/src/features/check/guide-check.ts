import type { GuideStepModel } from "@/features/guide";
import type { PouchItem } from "@/features/pouch";
import type { Choice } from "@/features/session";

import { similarity } from "./color";
import { isCompatible } from "./compat";

/** 사용자가 고른 것만 본다. 보유·대체는 판정하지 않는다 */
export type StepPick =
  { kind: "undecided" } | { kind: "picked"; item: PouchItem } | { kind: "skipped" };
export type PickKind = StepPick["kind"];

export interface CheckRow {
  step: GuideStepModel;
  pick: StepPick;
  /** 서버 매칭 제안. 연결 전까지 null */
  suggestion: null;
}

/** 고른 제품이 지워졌으면 미확정으로 본다 */
export function pickOf(
  stepId: string,
  choice: Record<string, Choice>,
  pouch: PouchItem[],
): StepPick {
  const ch = Object.hasOwn(choice, stepId) ? choice[stepId] : undefined;
  if (ch?.kind === "none") return { kind: "skipped" };
  if (ch?.kind === "pouch") {
    const item = pouch.find((p) => p.id === ch.id);
    if (item) return { kind: "picked", item };
  }
  return { kind: "undecided" };
}

export function checkRows(
  steps: GuideStepModel[],
  choice: Record<string, Choice>,
  pouch: PouchItem[],
): CheckRow[] {
  return steps.map((step) => ({
    step,
    pick: pickOf(step.stepId, choice, pouch),
    suggestion: null,
  }));
}

export function pickCounts(rows: CheckRow[]): Record<PickKind, number> {
  const counts = { undecided: 0, picked: 0, skipped: 0 };
  rows.forEach((r) => counts[r.pick.kind]++);
  return counts;
}

/** 기준색이 있으면 색이 가까운 순, 없으면 파우치 순서 */
export function candidatesFor(
  step: Pick<GuideStepModel, "makeup" | "matchCategory">,
  pouch: PouchItem[],
  refColor: string | null = null,
): PouchItem[] {
  const list = pouch.filter((p) => isCompatible(step, p));
  if (!refColor) return list;
  const score = (p: PouchItem) => (p.color ? similarity(refColor, p.color) : -1);
  return list
    .map((p) => ({ p, s: score(p) }))
    .sort((a, b) => b.s - a.s)
    .map((x) => x.p);
}

/** null이면 선택을 지운다 */
export function withChoice(
  choice: Record<string, Choice>,
  stepId: string,
  value: Choice | null,
): Record<string, Choice> {
  const next = { ...choice };
  if (value == null) delete next[stepId];
  else next[stepId] = value;
  return next;
}
