"use client";

import { useEffect, useMemo, useState } from "react";

import { pickOf, type StepPick } from "@/domain/check";
import {
  productRule,
  substituteReference,
  type GaugeLabel,
  type SelectedProduct,
} from "@/domain/gauge";
import { stepGauge } from "@/domain/guide";
import { getExecution } from "@/domain/guide-run";
import type { PouchItem } from "@/domain/pouch";
import type { Choice } from "@/domain/session";
import type { GuideArea } from "@/vision/guide";

import { subsOf, type TutorialStep } from "./tutorial-steps";

export const LABEL_TEXT: Record<GaugeLabel, string> = {
  lighter: "레퍼런스보다 연해요",
  similar: "레퍼런스와 비슷해요",
  darker: "레퍼런스보다 진해요",
};
export const LABEL_COLOR: Record<GaugeLabel, string> = {
  lighter: "#20DFFF",
  similar: "#2EF58C",
  darker: "#FF3E9D",
};

/**
 * 게이지에 쓸 고른 제품. 실행 정보를 못 받으면(모의 실행 · 조회 실패) 제품 체크에서 건너뛴 단계만 숨기고
 * 같은 제품으로 본다
 */
function selectedProduct(
  products: Record<string, SelectedProduct> | null,
  stepId: string,
  skipped: boolean,
): SelectedProduct {
  return products?.[stepId] ?? { result: skipped ? "NONE" : "SAME", selectedColor: null, skipped };
}

/** 실행 시작 때 서버가 확정한 단계별 제품 선택. 못 받으면 null이고 제품 체크 선택으로 대신한다 */
function useExecutionProducts(executionId: string | null) {
  const [products, setProducts] = useState<Record<string, SelectedProduct> | null>(null);
  useEffect(() => {
    if (!executionId) return;
    let live = true;
    getExecution(executionId)
      .then((execution) => {
        if (!live) return;
        setProducts(
          Object.fromEntries(
            execution.steps.map((s) => [
              s.stepId,
              {
                result: s.result,
                selectedColor: s.selectedColor,
                skipped: s.skipped,
              },
            ]),
          ),
        );
      })
      .catch((e) =>
        console.warn("실행의 제품 선택을 불러오지 못해 게이지는 제품 체크 선택으로 정합니다", e),
      );
    return () => {
      live = false;
    };
  }, [executionId]);
  return products;
}

/**
 * 지금 단계의 게이지 기준과 고른 제품에 따른 표시 규칙. 레퍼런스 게이지 기준이 있는 단계만 게이지를 띄우고,
 * 고른 제품에 따라 숨기거나 색감을 뺀다. 묶음 안 다음 단계가 게이지를 띄우는지도 함께 알려 준다
 */
export function useStepGaugeRule({
  steps,
  step,
  info,
  area,
  executionId,
  pick,
  choice,
  pouch,
  groupLast,
}: {
  steps: TutorialStep[];
  step: number;
  info: TutorialStep;
  area: GuideArea | null;
  executionId: string | null;
  /** 지금 단계의 제품 선택. 실제 가이드면 null */
  pick: StepPick | null;
  /** 다음 단계의 선택을 보려고 받는다 */
  choice: Record<string, Choice>;
  pouch: PouchItem[];
  /** 지금 단계가 묶음의 마지막이다 */
  groupLast: boolean;
}) {
  // 설명·제품과 얼굴 위 영역(GuideArea)은 단계 ID로 묶는다. 그릴 것이 없으면 설명만 보여 준다
  const subs = useMemo(() => subsOf(info, area), [area, info]);
  const reference = useMemo(() => stepGauge(subs), [subs]);
  const products = useExecutionProducts(executionId);
  // 실제 가이드의 선택은 표시만 하고 촬영·게이지 판단에는 쓰지 않는다
  const skipped = pick?.kind === "skipped";
  const product = useMemo(
    () => selectedProduct(products, info.stepId, skipped),
    [products, info.stepId, skipped],
  );
  const rule = useMemo(
    () => (reference ? productRule(reference.gauge, info.makeup, product) : null),
    [reference, info.makeup, product],
  );
  // 대체 제품 색이 레퍼런스와 멀면 그 제품 색 쪽으로 옮긴 기준으로 잰다
  const measureGauge = useMemo(() => {
    const hex = product.selectedColor?.hex;
    if (!reference || rule?.basis !== "product" || !hex) return reference?.gauge ?? null;
    return substituteReference(reference.gauge, hex);
  }, [reference, rule?.basis, product]);
  const measured = useMemo(
    () => subs.find((sub) => sub.subStepId === reference?.subStepId)?.guideSets ?? [],
    [subs, reference?.subStepId],
  );
  const madeSets = useMemo(() => subs.flatMap((sub) => sub.guideSets), [subs]);

  // 묶음 안 다음 단계가 게이지를 띄우면 그 단계 시작 기준이 필요하다
  const nextInfo = groupLast ? null : steps[step + 1];
  const nextSkipped = !!nextInfo && pickOf(nextInfo.stepId, choice, pouch).kind === "skipped";
  const nextNeedsBaseline = useMemo(() => {
    if (!nextInfo) return false;
    const ref = stepGauge(subsOf(nextInfo, area));
    const chosen = selectedProduct(products, nextInfo.stepId, nextSkipped);
    return !!ref && productRule(ref.gauge, nextInfo.makeup, chosen).show;
  }, [nextInfo, area, products, nextSkipped]);

  return {
    subs,
    reference,
    product,
    rule,
    measureGauge,
    measured,
    madeSets,
    showGauge: !!rule?.show,
    nextNeedsBaseline,
  };
}
