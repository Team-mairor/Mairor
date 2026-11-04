import { describe, expect, it, vi } from "vitest";

import { resolveStep } from "./area";
import type { AreaSubStep, GuideItem, GuideSet, GuideStep, TemplateId } from "./types";

const point = (triangle: number): GuideItem => ({
  type: "point",
  at: { triangle, bary: [1, 0, 0] },
});

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
const defaults: GuideSet = {
  meshVersion: "v1",
  steps: [
    { ...template("eyeshadow", 0), guides: [upper, under] },
    { ...template("eyeshadowUpper", 0), guides: [upper] },
    { ...template("eyeshadowUnder", 0), guides: [under] },
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

describe("resolveStep 아이섀도 템플릿", () => {
  it("eyeshadow와 바른 자리별 템플릿이 함께 오면 띠를 한 번만 그린다", () => {
    const step = resolveStep("s1", [sub(1, "eyeshadow"), sub(2, "eyeshadowUpper")], defaults);
    expect(step?.guides).toEqual([upper, under]);
  });

  it("eyeshadowUpper와 eyeshadowUnder만 오면 둘 다 그린다", () => {
    const step = resolveStep("s1", [sub(1, "eyeshadowUpper"), sub(2, "eyeshadowUnder")], defaults);
    expect(step?.guides).toEqual([upper, under]);
  });

  it("기본 가이드에 없는 템플릿은 경고하고 뺀다", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const step = resolveStep("s1", [sub(1, "lip")], defaults);
    expect(step).toBeNull();
    expect(warn).toHaveBeenCalledOnce();
    warn.mockRestore();
  });
});
