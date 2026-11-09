import { describe, expect, it, vi } from "vitest";

import type { FaceFrame } from "@/features/face";
import type { FaceMesh } from "@/features/overlay";

import { GuideRenderer, leftNormal } from "./renderer";
import type { GuideStep } from "./types";
import data from "../../../public/fixtures/faces/front.json";

const mesh: FaceMesh = {
  triangles: [
    [33, 7, 163],
    [263, 249, 390],
  ],
  uv: Array.from({ length: 478 }, () => [0.2, 0.5]),
};
const step: GuideStep = {
  stepId: "eyes",
  order: 1,
  title: "",
  regions: ["rightEye", "leftEye"],
  source: "extracted",
  guides: [
    { type: "point", region: "rightEye", at: { triangle: 0, bary: [1, 0, 0] } },
    { type: "point", region: "leftEye", at: { triangle: 1, bary: [1, 0, 0] } },
  ],
};

function renderer() {
  const ctx = {
    clearRect: vi.fn(),
    setTransform: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    setLineDash: vi.fn(),
    bezierCurveTo: vi.fn(),
  };
  const canvas = { width: 640, height: 480, getContext: () => ctx } as unknown as HTMLCanvasElement;
  return { ctx, renderer: new GuideRenderer(canvas) };
}
const render = (instance: GuideRenderer, frame: FaceFrame, now = 0, observed = frame) =>
  instance.render({
    frame,
    observedFrame: observed,
    step,
    mesh,
    projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
    now,
  });

describe("부위별 가이드 실제 그리기", () => {
  it("한 눈이 잘리면 그 눈 도형만 숨기고 보이는 눈은 그린다", () => {
    const { renderer: instance, ctx } = renderer();
    const frame = structuredClone(data) as FaceFrame;
    frame.regionVisibility.leftEye.inFrameRatio = 0.8;
    render(instance, frame);
    expect(ctx.fill).toHaveBeenCalledTimes(1);
    expect(instance.visibleRegions).toEqual(["rightEye"]);
  });

  it("그리기용 예측 위치가 화면 안으로 와도 실제 관측의 숨김 판정을 유지한다", () => {
    const { renderer: instance, ctx } = renderer();
    const observed = structuredClone(data) as FaceFrame;
    observed.regionVisibility.leftEye.inFrameRatio = 0;
    observed.regionVisibility.rightEye.inFrameRatio = 0;
    render(instance, data as FaceFrame, 0, observed);
    expect(ctx.fill).not.toHaveBeenCalled();
  });

  it("새 추론이 없어도 만료 시 화면을 지우고 그리지 않는다", () => {
    const { renderer: instance, ctx } = renderer();
    const frame = { ...data, detectedAt: 0 } as FaceFrame;
    render(instance, frame, 0);
    expect(ctx.fill).toHaveBeenCalledTimes(2);
    ctx.fill.mockClear();
    render(instance, frame, 301);
    expect(ctx.clearRect).toHaveBeenCalledTimes(2);
    expect(ctx.fill).not.toHaveBeenCalled();
  });
});

describe("얼굴 윤곽 단계의 먼 쪽", () => {
  const arrowStep: GuideStep = {
    stepId: "foundation",
    order: 1,
    title: "",
    regions: ["faceOval"],
    source: "extracted",
    // mesh의 UV 가로가 0.2라 본인 기준 오른쪽 볼 도형이다
    guides: [
      {
        type: "arrow",
        from: { triangle: 0, bary: [1, 0, 0] },
        to: { triangle: 0, bary: [0, 1, 0] },
      },
    ],
  };
  const drawArrow = (yaw: number) => {
    const { renderer: instance, ctx } = renderer();
    const frame = structuredClone(data) as FaceFrame;
    frame.pose.yaw = yaw;
    instance.render({
      frame,
      step: arrowStep,
      mesh,
      projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
      now: 0,
    });
    return ctx.stroke.mock.calls.length;
  };

  it("고개를 돌리면 먼 쪽 볼 화살표를 숨기고 가까운 쪽이면 그린다", () => {
    expect(drawArrow(0)).toBeGreaterThan(0);
    expect(drawArrow(-0.6)).toBe(0);
    expect(drawArrow(0.6)).toBeGreaterThan(0);
  });

  it("먼 쪽 끝점이 가운데 선을 넘어도 왼쪽 반쪽 방향을 유지한다", () => {
    const down = { x: 0, y: 1 };
    // 가운데 선이 x = 0일 때 왼쪽 끝은 +x 쪽
    expect(leftNormal(down, { x: -100, y: 0 }, { x: 100, y: 0 }).x).toBe(1);
    // 크게 돌려 왼쪽 끝이 가운데 선 반대편(x = -10)으로 넘어가도 오른쪽 끝보다 왼쪽에 있으면 같다
    expect(leftNormal(down, { x: -100, y: 0 }, { x: -10, y: 0 }).x).toBe(1);
  });
});

describe("여러 부위를 함께 판정하는 단계의 가운데 도형", () => {
  const centerMesh: FaceMesh = { ...mesh, uv: Array.from({ length: 478 }, () => [0.5, 0.5]) };
  const point = {
    type: "point" as const,
    at: { triangle: 0, bary: [1, 0, 0] as [number, number, number] },
  };
  const drawWithLipsCut = (regions: GuideStep["regions"]) => {
    const { renderer: instance, ctx } = renderer();
    const frame = structuredClone(data) as FaceFrame;
    frame.regionVisibility.lipsOuter.inFrameRatio = 0.5;
    instance.render({
      frame,
      step: { ...step, stepId: regions.join(), regions, guides: [point] },
      mesh: centerMesh,
      projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
      now: 0,
    });
    return ctx.fill.mock.calls.length;
  };

  it("입술이 잘려도 눈이 보이면 콧대 같은 가운데 도형을 그린다", () => {
    expect(drawWithLipsCut(["rightEye", "leftEye", "lipsOuter"])).toBe(1);
  });
  it("입술만 판정하는 단계는 입술이 잘리면 가운데 도형도 숨긴다", () => {
    expect(drawWithLipsCut(["lipsOuter"])).toBe(0);
  });
});

describe("영상 대신 까는 얼굴 윤곽", () => {
  it("부위별 가이드는 그려도 얼굴 전체 추적이 불안정하면 윤곽은 숨긴다", () => {
    const { renderer: instance, ctx } = renderer();
    const frame = structuredClone(data) as FaceFrame;
    frame.trackingState = "degraded";
    frame.usableRegions = ["rightEye"];
    instance.render({
      frame,
      step,
      mesh,
      projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
      now: 0,
      face: true,
    });
    expect(ctx.bezierCurveTo).not.toHaveBeenCalled();
    expect(ctx.fill).toHaveBeenCalledTimes(1);
  });
});
