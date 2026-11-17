import { categoryOfPart, type GuideModel, type MatchCategory } from "@/domain/guide";
import { templateOf } from "@/domain/guide-run";
import type { GuideAction, RefProduct } from "@/domain/session";
import type { RegionName } from "@/vision/face";
import { resolveStep, type GuideArea, type GuideSet, type Makeup } from "@/vision/guide";

import type { StepProduct } from "./step-cards";

/** 튜토리얼 한 단계에 필요한 실제 가이드 조회 응답 */
export interface TutorialStep {
  stepId: string;
  makeup: Makeup;
  /** 상단 바에서 묶는 부위 */
  category: MatchCategory | null;
  short: string;
  title: string;
  acts: GuideAction[];
  doneWhen: string | null;
  product: StepProduct | null;
  /** 샘플 매칭용 제품. 가이드 조회 응답은 아직 내 파우치와 맞춰 보지 않아 null */
  ref: RefProduct | null;
}

/** 가이드 조회 응답의 단계. 동작이 비면 요약 한 줄을 동작처럼 보여 준다 */
export function stepsOf(guide: GuideModel): TutorialStep[] {
  return guide.steps.map((s) => {
    const name = s.product?.name ?? s.product?.shade ?? null;
    return {
      stepId: s.stepId,
      makeup: s.makeup,
      category: s.matchCategory ?? categoryOfPart(s.makeup),
      short: s.label,
      title: s.label,
      acts: s.actions.length ? s.actions : s.summary ? [{ text: s.summary, tip: null }] : [],
      doneWhen: s.doneWhen,
      product: name
        ? {
            name,
            full: name,
            shade: s.product?.name ? s.product.shade : null,
            color: null,
            state: "unreg",
          }
        : null,
      ref: null,
    };
  });
}

/** 단계의 가이드 영역 하위 단계. 영역에 없는 단계는 화장 종류의 기본 가이드를 쓴다 */
export function subsOf(s: TutorialStep, area: GuideArea | null) {
  return area?.steps.find((a) => a.stepId === s.stepId)?.subSteps ?? [templateOf(s)];
}

/** 영역을 찾지 못한 단계도 화장 종류의 기본 가이드 부위를 써, 립 단계에서 입이 보일 때 입술을 찍는다 */
export function photoRegionsOf(
  s: TutorialStep,
  area: GuideArea | null,
  defaults: GuideSet | null,
): RegionName[] {
  const drawn = resolveStep(s.stepId, subsOf(s, area), defaults, s.makeup)?.regions ?? [];
  return drawn.length
    ? drawn
    : (resolveStep(s.stepId, [templateOf(s)], defaults, s.makeup)?.regions ?? []);
}

/** 묶음 안 다음 단계로 넘어갈 때 단계 제목 · 할 일(제품이 바뀌면 제품도)을 강조하는 시간(ms) */
export const ENTER_FLASH_MS = 1800;

export interface EnteredStep {
  step: number;
  product: string | null;
  changed: boolean;
}

export function enteredStepNotice({ product, changed }: EnteredStep) {
  if (changed) return product ? `제품을 바꿔 주세요 · ${product}` : "이 단계는 제품 없이 해요";
  return product ? "같은 제품으로 이어서 발라요" : "다음 단계예요";
}
