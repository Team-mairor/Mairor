import { describe, expect, it } from "vitest";

import { isGuideVisible, type FaceFrame } from "@/features/face";

import type { GuideStep } from "./types";
import { GuideVisibility, guideRegionAlpha, isStepVisible } from "./visibility";
import data from "../../../public/fixtures/faces/front.json";

const frame = (patch: Partial<FaceFrame> = {}): FaceFrame => ({
  ...(structuredClone(data) as FaceFrame),
  detectedAt: 0,
  ...patch,
});
const step: GuideStep = {
  stepId: "eyes",
  order: 1,
  title: "",
  source: "template",
  regions: ["leftEye", "rightEye"],
  guides: [],
};

describe("현재 단계의 부위별 표시", () => {
  it("381 크롭 안의 눈만 표시하고 크롭 변경을 같은 관측에도 반영한다", () => {
    const visibility = new GuideVisibility();
    const sample = frame();
    const points = sample.regions.rightEye.indices.map((i) => sample.landmarks[i]);
    const crop = {
      x0: 1 - Math.max(...points.map((p) => p.x)) - 0.01,
      x1: 1 - Math.min(...points.map((p) => p.x)) + 0.01,
      y0: Math.min(...points.map((p) => p.y)) - 0.01,
      y1: Math.max(...points.map((p) => p.y)) + 0.01,
    };
    expect(visibility.update(step, sample, 0, crop)).toBe(true);
    expect(visibility.alpha("rightEye")).toBe(1);
    expect(visibility.alpha("leftEye")).toBe(0);
    expect(visibility.update(step, sample, 0, { x0: 0, x1: 0.01, y0: 0, y1: 0.01 })).toBe(false);
  });
  it("크롭을 써도 먼 쪽 눈은 크롭이 없을 때와 같이 서서히 숨긴다", () => {
    const turned = frame({ pose: { yaw: 0.65, pitch: 0, roll: 0 } });
    turned.regionVisibility.leftEye.facing = false;
    const visibility = new GuideVisibility();
    visibility.update(step, turned, 0, { x0: 0, x1: 1, y0: 0, y1: 1 });
    const fading = guideRegionAlpha(turned, "leftEye");
    expect(fading).toBeGreaterThan(0);
    expect(fading).toBeLessThan(1);
    expect(visibility.alpha("leftEye")).toBe(fading);
  });
  it("시각이 같은 정적 픽스처로 바꿔도 다시 판정한다", () => {
    const visibility = new GuideVisibility();
    expect(visibility.update(step, frame({ timestamp: 0 }))).toBe(true);
    expect(visibility.update(step, frame({ timestamp: 0, trackingState: "lost" }))).toBe(false);
  });
  it("직접 지정한 화면 안 비율 기준을 그대로 적용한다", () => {
    const sample = frame();
    sample.regionVisibility.leftEye.inFrameRatio = 0.94;
    sample.regionVisibility.rightEye.inFrameRatio = 0.94;
    expect(isStepVisible(step, sample, 0.95)).toBe(false);
    expect(isStepVisible(step, sample, 0.9)).toBe(true);
  });

  it("전체 얼굴 가이드는 가까운 쪽 절반을 그릴 수 있도록 유지한다", () => {
    const turned = frame({
      trackingState: "degraded",
      usableRegions: ["faceOval"],
      pose: { yaw: 0.8, pitch: 0, roll: 0 },
    });
    expect(guideRegionAlpha(turned, "faceOval")).toBe(1);
  });
  it("전체 추적이 불안정해도 안정적으로 관측된 눈만 허용하고 기존 화장 판정은 유지한다", () => {
    const partial = frame({ trackingState: "degraded", usableRegions: ["rightEye"] });
    expect(isStepVisible(step, partial)).toBe(true);
    expect(guideRegionAlpha(partial, "rightEye")).toBe(1);
    expect(guideRegionAlpha(partial, "leftEye")).toBe(0);
    expect(isGuideVisible(partial)).toBe(false);
    expect(isStepVisible(step, frame({ trackingState: "degraded" }))).toBe(false);
  });

  it("고개를 돌려도 가까운 눈은 유지하고 먼 눈만 숨긴다", () => {
    const turned = frame({
      trackingState: "degraded",
      usableRegions: ["leftEye", "rightEye"],
      pose: { yaw: 0.8, pitch: 0, roll: 0 },
    });
    expect(guideRegionAlpha(turned, "leftEye")).toBe(0);
    expect(guideRegionAlpha(turned, "rightEye")).toBe(1);
    expect(isStepVisible(step, turned)).toBe(true);
  });

  it("부위별 복귀 여유를 그리기 횟수와 무관하게 적용한다", () => {
    const visibility = new GuideVisibility();
    const sample = frame();
    sample.regionVisibility.leftEye.inFrameRatio = 0.85;
    sample.regionVisibility.rightEye.inFrameRatio = 0.85;
    expect(visibility.update(step, sample)).toBe(false);
    const boundary = frame({ timestamp: 100 });
    boundary.regionVisibility.leftEye.inFrameRatio = 0.91;
    boundary.regionVisibility.rightEye.inFrameRatio = 0.91;
    expect(visibility.update(step, boundary)).toBe(false);
    expect(visibility.update(step, boundary)).toBe(false);
    boundary.timestamp = 200;
    boundary.regionVisibility.rightEye.inFrameRatio = 0.95;
    expect(visibility.update(step, boundary)).toBe(true);
    expect(visibility.alpha("leftEye")).toBe(0);
  });

  it("hold는 직전 표시만 잠깐 유지하고 오래된 관측과 새 단계는 숨긴다", () => {
    const visibility = new GuideVisibility();
    expect(visibility.update(step, frame())).toBe(true);
    const held = frame({ trackingState: "hold", timestamp: 150 });
    expect(visibility.update(step, held, 150)).toBe(true);
    expect(visibility.update(step, held, 301)).toBe(false);
    expect(visibility.update({ ...step, stepId: "next" }, held, 150)).toBe(false);
  });

  it("실제 관측 시각이 없는 정적 픽스처는 만료시키지 않는다", () => {
    expect(new GuideVisibility().update(step, data as FaceFrame, 100000)).toBe(true);
  });
});
