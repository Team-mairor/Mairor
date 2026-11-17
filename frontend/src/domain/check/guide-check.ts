import type { GuideStepModel } from "@/domain/guide";
import type { PouchItem } from "@/domain/pouch";
import type { Choice, MatchKind } from "@/domain/session";

import { similarity } from "./color";
import { isCompatible } from "./compat";
import type { NoneReason, StepMatch } from "./match-api";

/** 저장된 선택만 본다. 튜토리얼·리포트가 쓴다 */
export type StepPick =
  { kind: "undecided" } | { kind: "picked"; item: PouchItem } | { kind: "skipped" };
export type PickKind = StepPick["kind"];

/**
 * 매칭 결과가 없을 때의 이유. pending 맞추는 중, failed 매칭 실패,
 * unsupported 서버가 맞춰 보지 않는 단계(기타 화장), skipped 사용자가 생략을 고름
 */
export type NoMatchReason = "pending" | "failed" | "unsupported";
export type NoneKind = NoneReason | NoMatchReason | "skipped";

/** 제품 체크 화면의 단계별 결과. 사용자가 고른 것이 있으면 그것을, 없으면 서버 매칭을 쓴다 */
export type GuidePick =
  | { kind: "same"; item: PouchItem }
  | { kind: "sub"; item: PouchItem }
  | { kind: "none"; reason: NoneKind };

export interface CheckRow {
  step: GuideStepModel;
  pick: GuidePick;
  /** 서버가 고른 대체 후보(가까운 순). 파우치에서 지워진 제품은 뺀다 */
  candidates: PouchItem[];
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

const byRank = <T extends { rank: number }>(list: T[] = []) =>
  [...list].sort((a, b) => a.rank - b.rank);

/** 사용자가 직접 고른 선택. 시작할 때 자동으로 채운 것은 빼고 본다 */
export function userChoice(choice: Record<string, Choice>, stepId: string): Choice | undefined {
  const ch = Object.hasOwn(choice, stepId) ? choice[stepId] : undefined;
  return ch?.auto ? undefined : ch;
}

/** missing은 매칭 결과가 없을 때 보여 줄 이유 */
export function guidePick(
  stepId: string,
  choice: Record<string, Choice>,
  pouch: PouchItem[],
  match: StepMatch | undefined,
  missing: NoMatchReason = "unsupported",
): GuidePick {
  const find = (id: string | null) => (id ? pouch.find((p) => p.id === id) : undefined);
  const sameId = match?.result === "SAME" ? match.samePouchItemId : null;
  const ch = userChoice(choice, stepId);
  if (ch?.kind === "none") return { kind: "none", reason: "skipped" };
  const chosen = ch?.kind === "pouch" ? find(ch.id) : undefined;
  if (chosen) return { kind: chosen.id === sameId ? "same" : "sub", item: chosen };
  const same = find(sameId);
  if (same) return { kind: "same", item: same };
  const sub = byRank(match?.candidates)
    .map((c) => find(c.pouchItemId))
    .find(Boolean);
  if (sub) return { kind: "sub", item: sub };
  return { kind: "none", reason: match ? (match.noneReason ?? "NO_SUITABLE_ITEM") : missing };
}

export function checkRows(
  steps: GuideStepModel[],
  choice: Record<string, Choice>,
  pouch: PouchItem[],
  matches: Map<string, StepMatch>,
  missing: NoMatchReason = "unsupported",
): CheckRow[] {
  return steps.map((step) => {
    const match = matches.get(step.stepId);
    return {
      step,
      pick: guidePick(step.stepId, choice, pouch, match, missing),
      candidates: byRank(match?.candidates).flatMap(
        (c) => pouch.find((p) => p.id === c.pouchItemId) ?? [],
      ),
    };
  });
}

export function pickCounts(rows: CheckRow[]): Record<MatchKind, number> {
  const counts = { same: 0, sub: 0, none: 0 };
  rows.forEach((r) => counts[r.pick.kind]++);
  return counts;
}

/** 시작할 때 자동으로 채울 선택. 보유·대체는 그 제품, 없음은 생략 */
export function choiceOf(pick: GuidePick): Choice {
  return pick.kind === "none"
    ? { kind: "none", auto: true }
    : { kind: "pouch", id: pick.item.id, auto: true };
}

/**
 * 교체 목록은 서버가 고른 색 있는 호환 제품(색이 가까운 순)을 먼저 쓰고, 서버 목록에 없는
 * 같은 종류의 색 있는 보유 제품을 뒤에 붙인다. 그런 제품이 있으면 목록이 비지 않는다.
 */
export function swapList(row: CheckRow, pouch: PouchItem[], match?: StepMatch): PouchItem[] {
  const listed: { pouchItemId: string; rank: number; matchedColorHex?: string }[] | undefined =
    match?.alternatives ?? match?.candidates;
  const ranked = byRank(listed).flatMap((candidate) => {
    const item = pouch.find((p) => p.id === candidate.pouchItemId);
    if (!item) return [];
    return [candidate.matchedColorHex ? { ...item, color: candidate.matchedColorHex } : item];
  });
  const rest = candidatesFor(row.step, pouch).filter((p) => !ranked.some((r) => r.id === p.id));
  return [...ranked, ...rest];
}

/** 기준색이 있으면 색이 가까운 순, 없으면 파우치 순서 */
export function candidatesFor(
  step: Pick<GuideStepModel, "makeup">,
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
