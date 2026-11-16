// 측정 불가 판정과 값 안정화 값은 AI(Python)와 같이 쓰도록 shared/gauge/stability.v1.json에 둔다.
import { gaugeBar, type MeasureReason } from "./measure";
import raw from "../../../../shared/gauge/stability.v1.json" with { type: "json" };

export type FrameReason =
  "lost" | "turned" | "far" | "dark" | "bright" | "lightChanged" | "eyesClosed" | "covered";
/** 사진 거르기 이유, 게이지 값 계산이 낸 이유, 레퍼런스 효과가 작음, 단계 시작 기준 없음 */
export type GaugeReason = FrameReason | MeasureReason | "weakReference" | "noBaseline";
export type GaugeLabel = "lighter" | "similar" | "darker";

export const FRAME = raw.frame;
export const WINDOW = raw.window;
export const WEAK_TARGET_MIN: number = raw.weakTargetMin;
export const SMOOTHING = raw.smoothing;
export const HOLD_MS: number = raw.holdMs;
export const NEXT_START = raw.nextStart;
export const LABELS = raw.labels.names as GaugeLabel[];
const [LOW, HIGH] = raw.labels.bounds;
const MARGIN: number = raw.labels.margin;
const DWELL_MS: number = raw.labels.dwellMs;

/**
 * 사진 한 장의 상태. 빠진 값은 문제없는 값(각도 0, 눈 1, 얼굴 폭 1, 가림 0)이고
 * 밝기 · drift는 없으면 보지 않는다
 */
export interface FrameState {
  faces: number;
  /** 고개 각도(라디안) */
  yaw?: number;
  pitch?: number;
  roll?: number;
  /** 눈 뜬 정도(두 눈 중 작은 쪽) */
  eyes?: number;
  /** 얼굴 윤곽 폭 ÷ 영상 폭 */
  faceWidth?: number;
  /** 얼굴 가운데 평균 밝기(0~255) */
  brightness?: number | null;
  /** 맨피부가 단계 시작 기준에서 바뀐 크기(ΔE2000) */
  drift?: number | null;
  /** 지금 하위 단계 영역 칸 중 가린 몫(0~1) */
  areaCover?: number;
}

const FRAME_CHECKS: Record<FrameReason, (s: FrameState, makeup: string) => boolean> = {
  lost: (s) => s.faces !== 1,
  turned: (s) =>
    Math.abs(s.yaw ?? 0) > FRAME.yawMax ||
    Math.abs(s.roll ?? 0) > FRAME.rollMax ||
    Math.abs(s.pitch ?? 0) > FRAME.pitchMax,
  far: (s) => (s.faceWidth ?? 1) < FRAME.faceWidthMin,
  dark: (s) => s.brightness != null && s.brightness < FRAME.brightness[0],
  bright: (s) => s.brightness != null && s.brightness > FRAME.brightness[1],
  lightChanged: (s) => s.drift != null && s.drift > FRAME.driftMax,
  eyesClosed: (s, makeup) => FRAME.eyeMakeups.includes(makeup) && (s.eyes ?? 1) < FRAME.eyesOpenMin,
  covered: (s) => (s.areaCover ?? 0) > FRAME.areaCoverMax,
};

/** 사진 한 장을 게이지에 쓸 수 없는 이유. frame.order 순서로 처음 걸린 것, 쓸 수 있으면 null */
export function frameReason(state: FrameState, makeup: string): FrameReason | null {
  for (const reason of FRAME.order as FrameReason[]) {
    if (FRAME_CHECKS[reason](state, makeup)) return reason;
  }
  return null;
}

/**
 * 최근 창 사진들의 이유로 그 순간 잴 수 있는지. 쓸 수 있는 사진이 하나라도 있으면 null,
 * 없으면 가장 많이 나온 이유(같으면 먼저 나온 이유), 비었으면 lost
 */
export function windowReason(reasons: readonly (FrameReason | null)[]): FrameReason | null {
  if (reasons.length === 0) return "lost";
  if (reasons.includes(null)) return null;
  const counts = new Map<FrameReason, number>();
  for (const reason of reasons as FrameReason[]) counts.set(reason, (counts.get(reason) ?? 0) + 1);
  let best: FrameReason = "lost";
  let bestCount = 0;
  // Map은 처음 나온 순서라 더 많을 때만 바꾸면 같을 때 먼저 나온 이유가 남는다
  for (const [reason, count] of counts) {
    if (count > bestCount) [best, bestCount] = [reason, count];
  }
  return best;
}

/** 문구 번호(0 연해요 · 1 비슷해요 · 2 진해요)를 경계만 보고 정한다 */
export function labelOf(ratio: number): number {
  return ratio < LOW ? 0 : ratio > HIGH ? 2 : 1;
}

/** 지금 문구에서 여유를 넘어 떠날 문구 번호. 안 떠나면 그대로 */
export function leaveLabel(label: number, value: number): number {
  const up = [LOW, HIGH, Infinity][label];
  const down = [-Infinity, LOW, HIGH][label];
  if (value > up * (1 + MARGIN)) return label === 0 && value > HIGH * (1 + MARGIN) ? 2 : label + 1;
  if (value < down * (1 - MARGIN)) return label === 2 && value < LOW * (1 - MARGIN) ? 0 : label - 1;
  return label;
}

/** 게이지 값 계산 한 번의 결과 중 안정화에 쓰는 것. 못 쟀으면 ratio가 null */
export interface StabilizerInput {
  ratio: number | null;
  target: number | null;
  hueSame: boolean | null;
  chromaSame: boolean | null;
  reason?: MeasureReason | null;
}

/**
 * 게이지에 보일 값. 숨길 때는 ratio · bar · label이 null이고 reason에 이유가 든다.
 * stale은 못 재는 동안 마지막 값을 보이는 중인지다
 */
export interface GaugeDisplay {
  ratio: number | null;
  bar: number | null;
  label: GaugeLabel | null;
  reason: GaugeReason | null;
  stale: boolean;
  hueSame: boolean | null;
  chromaSame: boolean | null;
}

const hidden = (reason: GaugeReason): GaugeDisplay => ({
  ratio: null,
  bar: null,
  label: null,
  reason,
  stale: false,
  hueSame: null,
  chromaSame: null,
});

/** 하위 단계 하나의 게이지 값을 시간 순서대로 받아 보일 값을 낸다. 하위 단계가 바뀌면 새로 만든다 */
export class GaugeStabilizer {
  private value: number | null = null;
  private lastMs: number | null = null;
  private seenMs: number | null = null;
  private label: number | null = null;
  private pending: number | null = null;
  private pendingMs: number | null = null;
  private weak: boolean | null = null;
  private color: [boolean | null, boolean | null] = [null, null];

  /** nowMs에 잰 값을 받는다. 못 쟀으면 measure가 null이거나 ratio가 null이고 reason에 이유를 준다 */
  update(
    nowMs: number,
    measure: StabilizerInput | null,
    reason: GaugeReason | null = null,
  ): GaugeDisplay {
    const ratio = measure?.ratio ?? null;
    if (ratio !== null && this.weak === null) {
      this.weak = measure!.target != null && measure!.target < WEAK_TARGET_MIN;
    }
    if (this.weak) return hidden("weakReference");
    if (ratio !== null) {
      this.mix(nowMs, ratio);
      this.seenMs = nowMs;
      this.color = [measure!.hueSame, measure!.chromaSame];
      this.updateLabel(nowMs, this.value!);
      return this.show(false, null);
    }
    const missing = reason || measure?.reason || "lost";
    if (this.seenMs !== null && nowMs - this.seenMs <= HOLD_MS) return this.show(true, missing);
    this.label = this.pending = this.pendingMs = null;
    return hidden(missing);
  }

  private mix(nowMs: number, ratio: number) {
    if (this.value === null || this.lastMs === null) {
      this.value = ratio;
    } else {
      const steps = Math.max(nowMs - this.lastMs, 0) / SMOOTHING.perMs;
      const share = 1 - (1 - SMOOTHING.alpha) ** steps;
      this.value += share * (ratio - this.value);
    }
    this.lastMs = nowMs;
  }

  private updateLabel(nowMs: number, value: number) {
    if (this.label === null) {
      this.label = labelOf(value);
      return;
    }
    const target = leaveLabel(this.label, value);
    if (target === this.label) {
      this.pending = this.pendingMs = null;
      return;
    }
    if (this.pending !== target) [this.pending, this.pendingMs] = [target, nowMs];
    if (nowMs - this.pendingMs! >= DWELL_MS) {
      this.label = target;
      this.pending = this.pendingMs = null;
    }
  }

  private show(stale: boolean, reason: GaugeReason | null): GaugeDisplay {
    return {
      ratio: this.value,
      bar: this.value === null ? null : gaugeBar(this.value),
      label: this.label === null ? null : LABELS[this.label],
      reason,
      stale,
      hueSame: this.color[0],
      chromaSame: this.color[1],
    };
  }
}

/**
 * 묶음 둘째 단계부터 단계 시작 기준에 쓸 사진 번호. timesMs · reasons는 앞 단계 사진들의 시각과
 * frameReason(다음 단계 영역으로 판정), pressedMs는 「다음」을 누른 시각이다.
 * 직전 nextStart.windowMs 안에서 쓸 수 있는 사진 중 마지막 maxFrames장, minFrames장보다 적으면 null
 */
export function nextStartPicks(
  timesMs: readonly number[],
  reasons: readonly (FrameReason | null)[],
  pressedMs: number,
): number[] | null {
  if (timesMs.length !== reasons.length) throw new Error("timesMs와 reasons 길이가 다르다");
  const picks = timesMs
    .map((moment, index) => ({ moment, index }))
    .filter(
      ({ moment, index }) =>
        pressedMs - NEXT_START.windowMs <= moment && moment <= pressedMs && reasons[index] === null,
    )
    .map(({ index }) => index)
    .slice(-NEXT_START.maxFrames);
  return picks.length >= NEXT_START.minFrames ? picks : null;
}
