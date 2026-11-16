import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { REGIONS, type FaceFrame } from "@/features/face";
import { resolveAnchor, type FaceMesh } from "@/features/overlay";

import { buildDefaultGuideSet } from "./default-guides";
import { GuideRenderer, hiddenSideFor, leftNormal } from "./renderer";
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
  it("같은 눈 화살표라도 아이라인 단계의 윗라인만 눈 위로 옮긴다", () => {
    const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
    const realMesh = {
      ...read("../../../../shared/face-mesh/triangles.v1.json"),
      ...read("../../../../shared/face-mesh/uv.v1.json"),
    } as FaceMesh;
    const eyeshadow = buildDefaultGuideSet(realMesh, REGIONS).steps.find(
      (item) => item.stepId === "eyeshadowUpper",
    );
    const arrow = eyeshadow?.guides.find((guide) => guide.type === "arrow");
    if (!eyeshadow || arrow?.type !== "arrow") throw new Error("아이섀도 가이드가 없습니다");
    const renderEye = (eyelinerArrowOffset: boolean) => {
      const { renderer: instance, ctx } = renderer();
      instance.render({
        frame: data as FaceFrame,
        step: { ...eyeshadow, ...(eyelinerArrowOffset ? { eyelinerArrowOffset } : {}) },
        mesh: realMesh,
        projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
        now: 0,
      });
      return ctx.moveTo.mock.calls.at(-4);
    };
    const original = renderEye(false);
    const adjusted = renderEye(true);
    const from = resolveAnchor(arrow.from, realMesh, (data as FaceFrame).landmarks);
    expect(original).toEqual([from.x * 640, from.y * 480]);
    if (!original || !adjusted) throw new Error("눈 화살표가 그려지지 않았습니다");
    expect(adjusted[1]).toBeLessThan(original[1]);
  });

  it("아랫라인은 같은 눈의 모든 띠보다 아래로 화살표를 옮긴다", () => {
    const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
    const realMesh = {
      ...read("../../../../shared/face-mesh/triangles.v1.json"),
      ...read("../../../../shared/face-mesh/uv.v1.json"),
    } as FaceMesh;
    const under = buildDefaultGuideSet(realMesh, REGIONS).steps.find(
      (item) => item.stepId === "eyelinerUnder",
    );
    const line = under?.guides.find((guide) => guide.type === "polyline");
    if (!under || line?.type !== "polyline") throw new Error("아랫라인 가이드가 없습니다");
    const sorted = [...line.path].sort(
      (a, b) =>
        resolveAnchor(a, realMesh, (data as FaceFrame).landmarks).y -
        resolveAnchor(b, realMesh, (data as FaceFrame).landmarks).y,
    );
    const upperBand = {
      type: "polygon" as const,
      region: "rightEye" as const,
      outline: sorted.slice(0, 3),
    };
    const lowerBand = {
      type: "polygon" as const,
      region: "rightEye" as const,
      outline: sorted.slice(-3),
    };
    const direction = {
      type: "arrow" as const,
      region: "rightEye" as const,
      from: line.path[0],
      to: line.path.at(-1)!,
    };
    const draw = (guides: GuideStep["guides"]) => {
      const { renderer: instance, ctx } = renderer();
      instance.render({
        frame: data as FaceFrame,
        step: { ...under, eyelinerArrowOffset: true, guides },
        mesh: realMesh,
        projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
        now: 0,
      });
      return ctx.moveTo.mock.calls.at(-2)?.[1] as number;
    };
    expect(draw([upperBand, lowerBand, direction])).toBeGreaterThan(draw([upperBand, direction]));
  });

  it("윗라인 · 아랫라인을 한 번에 그려도 화살표는 자기 묶음 띠만 보고 옮긴다", () => {
    const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
    const realMesh = {
      ...read("../../../../shared/face-mesh/triangles.v1.json"),
      ...read("../../../../shared/face-mesh/uv.v1.json"),
    } as FaceMesh;
    const set = buildDefaultGuideSet(realMesh, REGIONS);
    const under = set.steps.find((item) => item.stepId === "eyelinerUnder");
    const line = under?.guides.find((guide) => guide.type === "polyline");
    const lid = set.steps
      .find((item) => item.stepId === "eyeshadowUpper")
      ?.guides.find((guide) => guide.type === "polygon");
    if (!under || line?.type !== "polyline" || lid?.type !== "polygon")
      throw new Error("눈 가이드가 없습니다");
    // 윗라인 하위 단계 띠(눈두덩)와 아랫라인 하위 단계 띠 · 화살표
    const upperBand = { ...lid, region: "rightEye" as const, group: "s12-1:rightEye" };
    const lowerBand = {
      type: "polygon" as const,
      region: "rightEye" as const,
      group: "s13-1:rightEye",
      outline: line.path,
    };
    const lowerArrow = {
      type: "arrow" as const,
      region: "rightEye" as const,
      group: "s13-1:rightEye",
      from: line.path[0],
      to: line.path.at(-1)!,
    };
    const draw = (guides: GuideStep["guides"]) => {
      const { renderer: instance, ctx } = renderer();
      instance.render({
        frame: data as FaceFrame,
        step: { ...under, eyelinerArrowOffset: true, guides },
        mesh: realMesh,
        projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
        now: 0,
      });
      return ctx.moveTo.mock.calls.at(-2)?.[1] as number;
    };
    expect(draw([upperBand, lowerBand, lowerArrow])).toBeCloseTo(draw([lowerBand, lowerArrow]), 6);
  });

  it("코 쉐딩 화살표는 눈 아래로 옮기지 않는다", () => {
    const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
    const realMesh = {
      ...read("../../../../shared/face-mesh/triangles.v1.json"),
      ...read("../../../../shared/face-mesh/uv.v1.json"),
    } as FaceMesh;
    const nose = buildDefaultGuideSet(realMesh, REGIONS).steps.find(
      (item) => item.stepId === "contourNose",
    );
    const arrow = nose?.guides.findLast((guide) => guide.type === "arrow");
    if (!nose || arrow?.type !== "arrow") throw new Error("코 쉐딩 가이드가 없습니다");
    const { renderer: instance, ctx } = renderer();
    instance.render({
      frame: data as FaceFrame,
      step: nose,
      mesh: realMesh,
      projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
      now: 0,
    });
    const from = resolveAnchor(arrow.from, realMesh, (data as FaceFrame).landmarks);
    expect(ctx.moveTo.mock.calls.at(-2)).toEqual([from.x * 640, from.y * 480]);
  });

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

  it("볼 부위에 묶인 가장자리 도형도 윤곽처럼 일찍 숨기고 볼 안쪽 도형은 그린다", () => {
    const draw = (u: number, yaw: number, earlyCheekEdgeTurn = true) => {
      const { renderer: instance, ctx } = renderer();
      const frame = structuredClone(data) as FaceFrame;
      frame.pose.yaw = yaw;
      instance.render({
        frame,
        step: {
          ...arrowStep,
          stepId: "contour",
          regions: ["rightCheek", "leftCheek"],
          earlyCheekEdgeTurn,
        },
        mesh: { ...mesh, uv: mesh.uv.map(() => [u, 0.5]) },
        projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
        now: 0,
      });
      return ctx.stroke.mock.calls.length;
    };
    expect(draw(0.05, -0.2)).toBeGreaterThan(0);
    expect(draw(0.05, -0.4)).toBe(0);
    expect(draw(0.05, 0.4)).toBeGreaterThan(0);
    expect(draw(0.3, -0.4)).toBeGreaterThan(0);
    expect(draw(0.05, -0.4, false)).toBeGreaterThan(0);
  });

  it("눈 가장자리 도형과 안쪽 도형은 함께 남긴다", () => {
    const { renderer: instance, ctx } = renderer();
    const frame = structuredClone(data) as FaceFrame;
    frame.pose.yaw = -0.4;
    instance.render({
      frame,
      step: {
        ...step,
        earlyCheekEdgeTurn: true,
        guides: [
          { type: "point", region: "rightEye", at: { triangle: 0, bary: [1, 0, 0] } },
          { type: "point", region: "rightEye", at: { triangle: 1, bary: [1, 0, 0] } },
        ],
      },
      mesh: {
        ...mesh,
        uv: mesh.uv.map((uv, i) => [i === 33 || i === 7 || i === 163 ? 0.05 : 0.3, uv[1]]),
      },
      projection: { toPx: (p) => ({ x: p.x * 640, y: p.y * 480 }), unit: 100 },
      now: 0,
    });
    expect(ctx.fill).toHaveBeenCalledTimes(2);
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

describe("미러필름 먼 쪽 숨김", () => {
  it("10° 넘게 돌리면 먼 쪽을 숨기고 5° 안으로 돌아와야 양쪽을 다시 그린다", () => {
    const deg = (d: number) => (d * Math.PI) / 180;
    expect(hiddenSideFor(null, deg(8))).toBe(null);
    expect(hiddenSideFor(null, deg(12))).toBe("left");
    expect(hiddenSideFor("left", deg(7))).toBe("left");
    expect(hiddenSideFor("left", deg(3))).toBe(null);
    expect(hiddenSideFor(null, deg(-12))).toBe("right");
  });
});
