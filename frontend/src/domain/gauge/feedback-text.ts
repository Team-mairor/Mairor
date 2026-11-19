// 단계 끝 평가 결과를 사용자가 읽을 안내 문장으로 바꾼다. AI tools/gauge/feedback_text.py와 같은 규칙이다.
// 기준값 · 문장 틀 · 낱말은 shared/gauge/feedback_text.v1.json에 둔다(낱말이 어색하면 그 파일만 고친다).
// 숫자 · 점수 · 합격 · 「잘했어요 / 실패」는 쓰지 않고, 문장과 평가 결과는 기록에 남기지 않는다.

import { SIDES, type Side, type SideScore } from "./step-evaluation";
import raw from "../../../../shared/gauge/feedback_text.v1.json" with { type: "json" };

export type MessageKey =
  "paintMore" | "fillSide" | "overflowSide" | "lighter" | "darker" | "similar" | "notChecked";
export type Where = "left" | "right";

/** 안내 문장 하나. 글자는 renderMessage로 만든다 */
export interface FeedbackMessage {
  key: MessageKey;
  subStepId: string;
  makeup: string;
  /** 좌우 짝에서 한쪽만 말할 때 그쪽(본인 기준, 거울 화면에서 보이는 쪽과 같다) */
  where: Where | null;
  side: Side | null;
  /** notChecked일 때 못 본 이유 */
  reason: string | null;
}

/** 문장을 고르는 데 필요한 평가 값. StepEvaluation이 그대로 들어간다 */
export interface FeedbackEvaluation {
  subStepId: string;
  coverage: number | null;
  overflow: number | null;
  sides: Record<Side, SideScore>;
  ratio: number | null;
  regions: readonly {
    region: string | null;
    coverage: number | null;
    overflow: number | null;
    sides: Record<Side, SideScore>;
    reason: string | null;
  }[];
  reason: string | null;
}

const THRESHOLDS = raw.thresholds;
const ORDER = raw.order as MessageKey[];
const AREA_KEYS: readonly MessageKey[] = ["paintMore", "fillSide", "overflowSide"];
const SILENT_MAKEUPS: readonly string[] = raw.silentMakeups;
const SILENT_REASONS: readonly string[] = raw.silentReasons;
const [LABEL_LOW, LABEL_HIGH] = raw.label.bounds;
const LABEL_MARGIN: number = raw.label.margin;

/** 부위 이름에서 본인 기준 왼쪽 · 오른쪽. 짝이 아닌 부위(입술 · 얼굴 윤곽)는 null이다 */
export function whereOf(region: string | null): Where | null {
  if (region === null) return null;
  if (region.startsWith("left")) return "left";
  if (region.startsWith("right")) return "right";
  return null;
}

const message = (
  key: MessageKey,
  subStepId: string,
  makeup: string,
  extra: Partial<Pick<FeedbackMessage, "where" | "side" | "reason">> = {},
): FeedbackMessage => ({ key, subStepId, makeup, where: null, side: null, reason: null, ...extra });

/** 기준을 넘은 방향 하나. fill이면 덮음이 limit보다 작은 방향 중 가장 빈 쪽, 아니면 넘침이 limit 이상인 방향 중 가장 많이 넘친 쪽이다 */
function pickSide(sides: Record<Side, SideScore>, limit: number, fill: boolean): Side | null {
  let best: { value: number; index: number; side: Side } | null = null;
  SIDES.forEach((side, index) => {
    const value = fill ? sides[side].coverage : sides[side].overflow;
    if (value === null || !(fill ? value < limit : value >= limit)) return;
    const rank = fill ? value : -value;
    if (!best || rank < best.value || (rank === best.value && index < best.index))
      best = { value: rank, index, side };
  });
  return (best as { side: Side } | null)?.side ?? null;
}

function combinedSide(
  sub: string,
  makeup: string,
  evaluation: FeedbackEvaluation,
  limit: number,
  key: MessageKey,
): FeedbackMessage[] {
  const side = pickSide(evaluation.sides, limit, key === "fillSide");
  return side === null ? [] : [message(key, sub, makeup, { side })];
}

function regionSides(
  sub: string,
  makeup: string,
  regions: FeedbackEvaluation["regions"],
  merge: boolean,
  limit: number,
  key: MessageKey,
): FeedbackMessage[] {
  const found: { where: Where | null; side: Side }[] = [];
  for (const region of regions) {
    const side = pickSide(region.sides, limit, key === "fillSide");
    if (side !== null) found.push({ where: whereOf(region.region), side });
  }
  if (
    merge &&
    found.length === regions.length &&
    regions.length > 1 &&
    new Set(found.map((f) => f.side)).size === 1
  )
    return [message(key, sub, makeup, { side: found[0].side })];
  return found.map((f) => message(key, sub, makeup, f));
}

function overflowOf(evaluation: FeedbackEvaluation, where: Where | null): number {
  if (where === null) return evaluation.overflow ?? 0;
  const region = evaluation.regions.find((r) => whereOf(r.region) === where);
  return region?.overflow ?? 0;
}

/** 하위 단계 하나의 안내 문장. 한 하위 단계에서 subMax개까지, 순서는 order다 */
export function stepMessages(evaluation: FeedbackEvaluation, makeup: string): FeedbackMessage[] {
  const sub = evaluation.subStepId;
  if (SILENT_MAKEUPS.includes(makeup)) return [];
  if (evaluation.reason !== null) {
    if (SILENT_REASONS.includes(evaluation.reason)) return [];
    return [message("notChecked", sub, makeup, { reason: evaluation.reason })];
  }
  const measured = evaluation.regions.filter((r) => r.coverage !== null);
  const pair = evaluation.regions.length > 1 && evaluation.regions.every((r) => whereOf(r.region));
  const both = pair && measured.length > 1;
  let out: FeedbackMessage[] = [];
  const told = new Set<Where | null>();
  if (pair) {
    const low = measured.filter((r) => r.coverage! < THRESHOLDS.coverageLow);
    if (both && low.length === measured.length) {
      out.push(message("paintMore", sub, makeup));
      for (const r of measured) told.add(whereOf(r.region));
    } else {
      for (const r of low) {
        out.push(message("paintMore", sub, makeup, { where: whereOf(r.region) }));
        told.add(whereOf(r.region));
      }
    }
  } else if (evaluation.coverage !== null && evaluation.coverage < THRESHOLDS.coverageLow) {
    out.push(message("paintMore", sub, makeup));
    told.add(null);
  }
  const rest = pair ? measured.filter((r) => !told.has(whereOf(r.region))) : [];
  if (pair && raw.sideWhere === "regions") {
    out = out.concat(
      regionSides(
        sub,
        makeup,
        rest,
        both && told.size === 0,
        THRESHOLDS.sideCoverageLow,
        "fillSide",
      ),
      regionSides(sub, makeup, measured, both, THRESHOLDS.sideOverflowHigh, "overflowSide"),
    );
  } else {
    if (told.size === 0)
      out = out.concat(
        combinedSide(sub, makeup, evaluation, THRESHOLDS.sideCoverageLow, "fillSide"),
      );
    out = out.concat(
      combinedSide(sub, makeup, evaluation, THRESHOLDS.sideOverflowHigh, "overflowSide"),
    );
  }
  if (told.size > 0)
    out = out.filter(
      (m) =>
        m.key !== "overflowSide" ||
        (m.where !== null && !told.has(m.where) && !told.has(null)) ||
        overflowOf(evaluation, m.where) >= THRESHOLDS.toldOverflowMin,
    );
  if (evaluation.ratio !== null) {
    const label =
      evaluation.ratio < LABEL_LOW * (1 - LABEL_MARGIN)
        ? "lighter"
        : evaluation.ratio > LABEL_HIGH * (1 + LABEL_MARGIN)
          ? "darker"
          : "similar";
    if (label === "darker" || (label === "lighter" && !out.some((m) => m.key === "paintMore")))
      out.push(message(label, sub, makeup));
    else if (label === "similar" && !out.some((m) => AREA_KEYS.includes(m.key)))
      out.push(message("similar", sub, makeup));
  }
  if (pair)
    for (const r of evaluation.regions)
      if (r.reason === "covered")
        out.push(
          message("notChecked", sub, makeup, { where: whereOf(r.region), reason: "covered" }),
        );
  out.sort((a, b) => ORDER.indexOf(a.key) - ORDER.indexOf(b.key));
  return out.slice(0, raw.subMax);
}

/** 문장 틀의 {이름} 자리에 낱말을 채운 한국어 문장 */
export function renderMessage(m: FeedbackMessage): string {
  const parts: Record<string, string> =
    raw.parts[m.makeup as keyof typeof raw.parts] ?? raw.parts.other;
  const sideWords: Record<string, string> =
    raw.sideWords[m.makeup as keyof typeof raw.sideWords] ?? raw.sideWords.other;
  const reasonWords: Record<string, string> = raw.reasonWords;
  const words: Record<string, string> = {
    ...parts,
    where: m.where === null ? "" : raw.whereWords[m.where],
    side: m.side === null ? "" : sideWords[m.side],
    reason: m.reason === null ? "" : (reasonWords[m.reason] ?? ""),
  };
  return raw.texts[m.key].replace(/\{(\w+)\}/g, (_, name: string) => words[name] ?? "");
}

/**
 * 묶음 끝에 보일 문장. steps는 하위 단계 순서대로 각 하위 단계의 stepMessages다.
 * 하위 단계마다 첫 문장을 먼저, 남는 자리에 둘째 문장을 같은 순서로 놓아 bundleMax개까지 보인다.
 * 같은 글자가 되는 문장은 앞의 것만 남긴다
 */
export function bundleMessages(steps: readonly (readonly FeedbackMessage[])[]): FeedbackMessage[] {
  const depth = Math.max(0, ...steps.map((s) => s.length));
  const queue: FeedbackMessage[] = [];
  for (let rank = 0; rank < depth; rank++)
    for (const step of steps) if (rank < step.length) queue.push(step[rank]);
  const out: FeedbackMessage[] = [];
  const seen = new Set<string>();
  for (const m of queue) {
    const text = renderMessage(m);
    if (seen.has(text)) continue;
    seen.add(text);
    out.push(m);
    if (out.length >= raw.bundleMax) break;
  }
  return out;
}
