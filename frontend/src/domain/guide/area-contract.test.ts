import { readFileSync } from "node:fs";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveStep } from "@/vision/guide/area";
import { checkGuideArea } from "@/vision/guide/guide-overlay";

import { toGuideArea, toGuideModel } from "./guide-model";

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const meshFile = (name: string) =>
  readFileSync(new URL(`../../../../shared/face-mesh/${name}`, import.meta.url), "utf8");

const anchor = (triangle: number) => ({ triangle, bary: [0.2, 0.3, 0.5] });
const polygon = { type: "polygon", outline: [anchor(10), anchor(11), anchor(12)] };
const arrow = { type: "arrow", from: anchor(10), to: anchor(12) };
const brokenArrow = { type: "arrow", from: anchor(999999), to: anchor(12) };

/** 가이드 조회 응답 그대로의 한 단계 */
const response = (guides: unknown[]) => ({
  guideId: GUIDE_ID,
  guideVersion: 1,
  meshVersion: "v1",
  steps: [
    {
      stepId: "s1",
      order: 1,
      type: "GUIDE",
      part: "eyeshadow",
      partLabel: "아이섀도",
      summary: null,
      actions: [],
      subSteps: [
        {
          subStepId: "s1-1",
          order: 1,
          status: "extracted",
          reasons: [],
          templateId: null,
          guideSets: [{ region: "rightEye", source: "extracted", guides }],
        },
      ],
    },
  ],
});

/** 응답 → 화면 모델 → 영역 검사 → 그릴 가이드 */
async function drawn(guides: unknown[]) {
  const area = toGuideArea(toGuideModel(response(guides), GUIDE_ID))!;
  const checked = await checkGuideArea(area, "test");
  const sub = checked.steps[0].subSteps[0];
  return { sub, step: resolveStep("s1", checked.steps[0].subSteps, null) };
}

beforeEach(() => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json(
        JSON.parse(meshFile(url.includes("triangles") ? "triangles.v1.json" : "uv.v1.json")),
      ),
    ),
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("가이드 조회 응답의 영역·화살표 검사", () => {
  it("영역과 화살표가 함께 오면 둘 다 그린다", async () => {
    const { sub, step } = await drawn([polygon, arrow]);
    expect(sub.status).toBe("extracted");
    expect(step?.guides.map((g) => g.type)).toEqual(["polygon", "arrow"]);
  });

  it("잘못된 화살표만 빼고 영역은 계속 그린다", async () => {
    const { sub, step } = await drawn([polygon, brokenArrow]);
    expect(sub.status).toBe("extracted");
    expect(step?.guides.map((g) => g.type)).toEqual(["polygon"]);
  });

  it("도형 목록에 빈 값이 섞여도 그 값만 뺀다", async () => {
    const { sub, step } = await drawn([polygon, null]);
    expect(sub.status).toBe("extracted");
    expect(step?.guides.map((g) => g.type)).toEqual(["polygon"]);
  });

  it("영역 없이 화살표만 오면 그 묶음을 빼고 하위 단계를 실패로 본다", async () => {
    const { sub, step } = await drawn([arrow]);
    expect(sub.status).toBe("failed");
    expect(step).toBeNull();
  });
});
