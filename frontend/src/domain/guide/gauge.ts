import type { AreaSubStep, GaugeReference } from "@/vision/guide/types";

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isLab = (v: unknown): v is [number, number, number] =>
  Array.isArray(v) && v.length === 3 && v.every(Number.isFinite);
const DIRECTIONS = new Set<unknown>(["darker", "lighter", "same"]);
const isColor = (v: unknown): v is NonNullable<GaugeReference["color"]> =>
  isRecord(v) && typeof v.hex === "string" && /^#[0-9a-f]{6}$/i.test(v.hex) && isLab(v.lab);

/**
 * 가이드 조회 응답의 gauge를 검사한다. 없거나 모양이 틀리면 기준 없음(null)이다.
 * 흰자 색은 없거나 모양이 틀리면 null로 두어, 흰자로 맞추는 화장만 noWhite로 숨긴다
 */
export function gaugeOf(v: unknown): GaugeReference | null {
  if (!isRecord(v)) return null;
  const { color, effect, strength, reason } = v;
  const colorOk = color === null || isColor(color);
  const effectOk =
    effect === null ||
    (isRecord(effect) &&
      isLab(effect.delta) &&
      typeof effect.size === "number" &&
      Number.isFinite(effect.size) &&
      effect.size >= 0 &&
      DIRECTIONS.has(effect.direction));
  const strengthOk =
    strength === null || (typeof strength === "number" && Number.isFinite(strength));
  const reasonOk = reason === null || typeof reason === "string";
  if (!colorOk || !effectOk || !strengthOk || !reasonOk) return null;
  const white = isColor(v.white) ? v.white : null;
  return { ...(v as unknown as GaugeReference), white };
}

/** 게이지 막대를 그릴 수 있는 하위 단계 기준 */
export interface StepGauge {
  subStepId: string;
  gauge: GaugeReference & { effect: NonNullable<GaugeReference["effect"]> };
}

/**
 * 단계의 게이지 기준. 튜토리얼은 한 단계의 하위 단계를 한 번에 그리므로 값이 있는 첫 하위 단계의 기준을 쓴다.
 * 이유가 있거나 효과가 없는 기준은 다른 하위 단계 값으로 대신하고, 하나도 없으면 null(게이지 숨김)이다
 */
export function stepGauge(subs: AreaSubStep[]): StepGauge | null {
  for (const sub of [...subs].sort((a, b) => a.order - b.order)) {
    const gauge = sub.gauge;
    if (gauge && !gauge.reason && gauge.effect && gauge.effect.size > 0)
      return { subStepId: sub.subStepId, gauge: gauge as StepGauge["gauge"] };
  }
  return null;
}
