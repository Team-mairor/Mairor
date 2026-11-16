import { describe, expect, it, vi } from "vitest";

import { resolveStep, resolveSubStep } from "./area";
import type { AreaSubStep, GuideItem, GuideSet, GuideStep, TemplateId } from "./types";

const point = (triangle: number): GuideItem => ({
  type: "point",
  at: { triangle, bary: [1, 0, 0] },
});

const anchor = (triangle: number) => ({ triangle, bary: [1, 0, 0] as [number, number, number] });

const template = (stepId: string, triangle: number): GuideStep => ({
  stepId,
  order: 1,
  title: stepId,
  regions: ["rightEye", "leftEye"],
  guides: [point(triangle)],
  source: "template",
});

const upper = point(1);
const under = point(2);
const lowerLine = point(6);
const defaults: GuideSet = {
  meshVersion: "v1",
  steps: [
    { ...template("eyeshadow", 0), guides: [upper, under] },
    { ...template("eyeshadowUpper", 0), guides: [upper] },
    { ...template("eyeshadowUnder", 0), guides: [under] },
    { ...template("eyelinerUnder", 0), guides: [lowerLine] },
    { ...template("blush", 0), guides: [point(7)] },
    { ...template("blushNose", 0), guides: [point(8)] },
  ],
};

const sub = (order: number, templateId: TemplateId): AreaSubStep => ({
  subStepId: `s1-${order}`,
  order,
  status: "template",
  reasons: ["eyeshadowColorNotFound"],
  templateId,
  guideSets: [],
});

const extracted = (
  order: number,
  guides: AreaSubStep["guideSets"][number]["guides"],
): AreaSubStep => ({
  subStepId: `s1-${order}`,
  order,
  status: "extracted",
  reasons: [],
  templateId: null,
  guideSets: [{ region: "rightEye", source: "extracted", guides }],
});

describe("resolveStep 아이섀도 템플릿", () => {
  it("쉐딩 단계의 분석 도형에만 볼 가장자리 이른 숨김을 표시한다", () => {
    const area = extracted(1, [{ type: "arrow", from: anchor(0), to: anchor(1) }]);
    expect(resolveStep("arbitrary-id", [area], defaults, "contour")?.earlyCheekEdgeTurn).toBe(true);
    expect(resolveStep("arbitrary-id", [area], defaults, "blush")?.earlyCheekEdgeTurn).toBe(false);
  });

  it("아이라인 단계에만 화살표 위치 보정을 지정한다", () => {
    const area = extracted(1, [{ type: "arrow", from: anchor(0), to: anchor(1) }]);
    expect(resolveStep("arbitrary-id", [area], defaults, "eyeliner")?.eyelinerArrowOffset).toBe(
      true,
    );
    expect(resolveStep("arbitrary-id", [area], defaults, "eyeshadow")?.eyelinerArrowOffset).toBe(
      undefined,
    );
    expect(resolveSubStep(area, defaults, "eyeliner")?.eyelinerArrowOffset).toBe(true);
  });

  it("AI 영역 묶음의 부위 정보를 각 도형에 유지한다", () => {
    const polygon = {
      type: "polygon" as const,
      outline: [{ triangle: 1, bary: [1, 0, 0] as [number, number, number] }],
    };
    const resolved = resolveSubStep(
      {
        ...sub(1, "eyeshadow"),
        status: "extracted",
        guideSets: [
          { region: "rightEye", source: "extracted", guides: [polygon], exclude: ["rightEye"] },
        ],
      },
      defaults,
    );
    expect(resolved?.guides[0]).toEqual({
      ...polygon,
      region: "rightEye",
      group: "s1-1:rightEye",
      exclude: ["rightEye"],
    });
  });
  it("eyeshadow와 바른 자리별 템플릿이 함께 오면 띠를 한 번만 그린다", () => {
    const step = resolveStep("s1", [sub(1, "eyeshadow"), sub(2, "eyeshadowUpper")], defaults);
    expect(step?.guides).toEqual([upper, under]);
  });

  it("eyeshadowUpper와 eyeshadowUnder만 오면 둘 다 그린다", () => {
    const step = resolveStep("s1", [sub(1, "eyeshadowUpper"), sub(2, "eyeshadowUnder")], defaults);
    expect(step?.guides).toEqual([upper, under]);
  });

  it("찾은 영역과 찾지 못한 자리의 기본 가이드를 하위 단계 순서대로 함께 그린다", () => {
    const polygon = {
      type: "polygon" as const,
      outline: [anchor(3), anchor(4), anchor(5)],
    };
    const step = resolveStep("s1", [extracted(1, [polygon]), sub(2, "eyeshadowUnder")], defaults);

    expect(step?.guides).toEqual([
      { ...polygon, region: "rightEye", group: "s1-1:rightEye" },
      under,
    ]);
    expect(step?.source).toBe("template");
  });

  it("윗라인을 찾고 아랫라인을 못 찾으면 찾은 윗라인과 아래 선 기본 가이드를 함께 그린다", () => {
    const polygon = {
      type: "polygon" as const,
      outline: [anchor(3), anchor(4), anchor(5)],
    };
    const step = resolveStep("s1", [extracted(1, [polygon]), sub(2, "eyelinerUnder")], defaults);

    expect(step?.guides).toEqual([
      { ...polygon, region: "rightEye", group: "s1-1:rightEye" },
      lowerLine,
    ]);
    expect(step?.source).toBe("template");
  });

  it("하위 단계가 순서와 다르게 와도 order 순서대로 그린다", () => {
    const step = resolveStep("s1", [sub(2, "eyeshadowUnder"), sub(1, "eyeshadowUpper")], defaults);

    expect(step?.guides).toEqual([upper, under]);
    expect(step?.order).toBe(1);
  });

  it("찾은 영역의 시작점·방향 화살표를 영역과 함께 유지한다", () => {
    const polygon = {
      type: "polygon" as const,
      outline: [anchor(3), anchor(4), anchor(5)],
    };
    const arrow = { type: "arrow" as const, from: anchor(3), to: anchor(4) };

    expect(resolveStep("s1", [extracted(1, [polygon, arrow])], defaults)?.guides).toEqual([
      { ...polygon, region: "rightEye", group: "s1-1:rightEye" },
      { ...arrow, region: "rightEye", group: "s1-1:rightEye" },
    ]);
  });

  it("볼 블러셔와 코 블러셔 키는 서로 다른 기본 가이드를 그린다", () => {
    expect(resolveStep("s21", [sub(1, "blush")], defaults, "blush")?.guides).toEqual([point(7)]);
    expect(resolveStep("s22b", [sub(1, "blushNose")], defaults, "blush")?.guides).toEqual([
      point(8),
    ]);
  });

  it("기본 가이드에 없는 템플릿은 경고하고 뺀다", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const step = resolveStep("s1", [sub(1, "lip")], defaults);
    expect(step).toBeNull();
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
