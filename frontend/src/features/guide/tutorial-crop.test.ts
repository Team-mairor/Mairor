import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import type { FaceFrame, Point } from "@/features/face";

import {
  TABLET_WIDTH,
  TABLET_HEIGHT,
  TUTORIAL_TOP,
  TUTORIAL_BOTTOM,
  cropTransform,
  validCrop,
  isStepInCrop,
  tabletPreviewScale,
  writeTutorialCrop,
  CROP_KEY,
  tutorialVideoRatio,
  centeredTutorialCrop,
  resizeTutorialCrop,
} from "./tutorial-crop";
import type { GuideStep } from "./types";

const crop = { x0: 0.1, y0: 0.2, x1: 0.9, y1: 0.8 };
describe("카메라 준비와 영역 조정", () => {
  it("메타데이터가 없거나 영상이 비워지면 비율을 사용하지 않는다", () => {
    expect(tutorialVideoRatio(null)).toBeNull();
    expect(tutorialVideoRatio({ readyState: 0, videoWidth: 1920, videoHeight: 1080 })).toBeNull();
    expect(tutorialVideoRatio({ readyState: 1, videoWidth: 0, videoHeight: 1080 })).toBeNull();
    expect(tutorialVideoRatio({ readyState: 1, videoWidth: 1920, videoHeight: 0 })).toBeNull();
  });
  it("영상이 준비되면 실제 해상도에서 비율을 읽는다", () => {
    expect(tutorialVideoRatio({ readyState: 1, videoWidth: 1920, videoHeight: 1080 })).toBe(16 / 9);
    expect(tutorialVideoRatio({ readyState: 4, videoWidth: 640, videoHeight: 480 })).toBe(4 / 3);
  });
  it("가로·세로 카메라 모두 실제 영상에서 800×688 영역을 잡는다", () => {
    for (const ratio of [4 / 3, 16 / 9, 9 / 16]) {
      const rect = centeredTutorialCrop(ratio);
      expect(validCrop(rect)).toBe(true);
      expect(((rect.x1 - rect.x0) * ratio) / (rect.y1 - rect.y0)).toBeCloseTo(800 / 688);
      expect(rect.x0 + rect.x1).toBeCloseTo(1);
      expect(rect.y0 + rect.y1).toBeCloseTo(1);
    }
  });
  it("최소·최대 크기로 줄이거나 늘려도 저장 가능한 범위와 tutorial 비율을 지킨다", () => {
    for (const ratio of [4 / 3, 16 / 9, 9 / 16]) {
      for (const width of [-10, 0.01, 0.5, 10]) {
        const rect = resizeTutorialCrop(centeredTutorialCrop(ratio), width, ratio);
        expect(validCrop(rect)).toBe(true);
        expect(((rect.x1 - rect.x0) * ratio) / (rect.y1 - rect.y0)).toBeCloseTo(800 / 688);
      }
    }
  });
  it("가장자리에서 최소 크기를 확보할 수 없으면 원래 영역을 유지한다", () => {
    const rect = { x0: 0.94, y0: 0.94, x1: 1, y1: 1 };
    const resized = resizeTutorialCrop(rect, 10, 16 / 9);
    expect(resized).toEqual(rect);
    expect(validCrop(resized)).toBe(true);
  });
});
describe("tutorial crop", () => {
  it("갤탭 앱의 표시 영역은 PC 창 크기와 무관하게 800×688이다", () => {
    expect(TABLET_WIDTH).toBe(800);
    expect(TABLET_HEIGHT).toBe(1200);
    expect(TABLET_HEIGHT - TUTORIAL_TOP - TUTORIAL_BOTTOM).toBe(688);
  });
  it("잘못되거나 너무 작거나 영상 밖인 저장값은 거부한다", () => {
    for (const value of [
      null,
      {},
      { ...crop, x0: -0.1 },
      { ...crop, x1: 2 },
      { ...crop, y1: 0.21 },
      { ...crop, x0: NaN },
      { ...crop, x0: "0.1" },
    ]) {
      expect(validCrop(value)).toBe(false);
    }
    expect(validCrop(crop)).toBe(true);
  });
  it("선택 영역을 같은 배율로 맞추고 좌우 거울 방향을 유지한다", () => {
    const view = cropTransform({ width: 640, height: 480 }, { width: 800, height: 450 }, crop);
    expect(view.mirrored).toBe(true);
    expect((crop.x1 - crop.x0) * 640 * view.scale).toBeCloseTo(800);
    expect((crop.y1 - crop.y0) * 480 * view.scale).toBeCloseTo(450);
    expect(crop.x0 * 640 * view.scale + view.offsetX).toBeCloseTo(0);
    expect(crop.y0 * 480 * view.scale + view.offsetY).toBeCloseTo(0);
  });
  it("다른 화면 비율에서도 영역을 늘리지 않고 가운데 배치한다", () => {
    const v = cropTransform({ width: 640, height: 480 }, { width: 400, height: 800 }, crop);
    expect((crop.x1 - crop.x0) * 640 * v.scale).toBeCloseTo(400);
    const top = crop.y0 * 480 * v.scale + v.offsetY;
    const bottom = crop.y1 * 480 * v.scale + v.offsetY;
    expect(top).toBeGreaterThan(0);
    expect(800 - bottom).toBeCloseTo(top);
  });
});

const front: FaceFrame = JSON.parse(
  readFileSync(new URL("../../../public/fixtures/faces/front.json", import.meta.url), "utf8"),
);
const step: GuideStep = {
  stepId: "eye",
  order: 1,
  title: "",
  source: "template",
  regions: ["rightEye"],
  guides: [],
};
const frameFor = (points: Point[]) => {
  const frame = structuredClone(front);
  points.forEach((p, i) => {
    frame.landmarks[i] = { x: 1 - p.x, y: p.y };
  });
  frame.regions.rightEye.indices = points.map((_, i) => i);
  frame.regions.faceOval.indices = points.map((_, i) => i);
  frame.regionVisibility.rightEye.facing = true;
  return frame;
};
const box = (x0: number, x1: number): Point[] => [
  { x: x0, y: 0.3 },
  { x: x1, y: 0.3 },
  { x: x1, y: 0.6 },
  { x: x0, y: 0.6 },
];
const display = { x0: 0.2, y0: 0.2, x1: 0.8, y1: 0.8 };
describe("크롭 화면 밖 판정", () => {
  it("카메라 안에 있어도 표시 영역을 벗어나면 안내하고 돌아오면 복구한다", () => {
    expect(isStepInCrop(step, frameFor(box(0.3, 0.5)), display)).toBe(true);
    expect(isStepInCrop(step, frameFor(box(0.01, 0.15)), display)).toBe(false);
    expect(isStepInCrop(step, frameFor(box(0.3, 0.5)), display, 0.03)).toBe(true);
  });
  it("원본 좌우를 거울 방향으로 바꿔 판정한다", () => {
    const frame = frameFor(box(0.1, 0.2));
    expect(isStepInCrop(step, frame, { x0: 0.05, y0: 0.1, x1: 0.3, y1: 0.9 })).toBe(true);
    expect(isStepInCrop(step, frame, { x0: 0.7, y0: 0.1, x1: 0.95, y1: 0.9 })).toBe(false);
  });
  it("살짝 잘린 부위는 유지하고 완전히 벗어나거나 경계만 닿으면 숨긴다", () => {
    expect(isStepInCrop(step, frameFor(box(0.1, 0.4)), display)).toBe(true);
    expect(isStepInCrop(step, frameFor(box(0, 0.2)), display)).toBe(false);
    expect(isStepInCrop(step, frameFor(box(0.001, 0.201)), display, 0.03)).toBe(false);
  });
  it("가이드 없는 단계도 얼굴 윤곽을 기준으로 판정한다", () => {
    expect(isStepInCrop(null, frameFor(box(0.01, 0.15)), display)).toBe(false);
  });
  it("카메라에서 가려진 부위는 크롭 안에 있어도 표시 대상으로 보지 않는다", () => {
    const frame = frameFor(box(0.3, 0.5));
    frame.regionVisibility.rightEye.facing = false;
    expect(isStepInCrop(step, frame, display)).toBe(false);
  });
});
describe("미리보기 크기와 저장 실패", () => {
  it("작은 창에서도 갤탭 프레임이 여백 안에 들어간다", () => {
    for (const screen of [
      { width: 80, height: 90 },
      { width: 320, height: 200 },
      { width: 1920, height: 1080 },
    ]) {
      const scale = tabletPreviewScale(screen);
      expect(800 * scale).toBeLessThanOrEqual(screen.width - 32 + 1e-9);
      expect(1200 * scale).toBeLessThanOrEqual(screen.height - 32 + 1e-9);
    }
    expect(tabletPreviewScale({ width: 20, height: 20 })).toBe(0);
  });
  it("저장·초기화 실패를 모두 호출자에게 알린다", () => {
    const storage = {
      setItem: vi.fn(() => {
        throw new Error("blocked");
      }),
      removeItem: vi.fn(() => {
        throw new Error("blocked");
      }),
    };
    expect(writeTutorialCrop(storage, display)).toBe(false);
    expect(writeTutorialCrop(storage, null)).toBe(false);
  });
  it("저장·삭제에 같은 키를 쓰고 잘못된 값은 저장하지 않는다", () => {
    const storage = { setItem: vi.fn(), removeItem: vi.fn() };
    expect(writeTutorialCrop(storage, display)).toBe(true);
    expect(storage.setItem).toHaveBeenCalledWith(CROP_KEY, JSON.stringify(display));
    expect(writeTutorialCrop(storage, null)).toBe(true);
    expect(storage.removeItem).toHaveBeenCalledWith(CROP_KEY);
    expect(writeTutorialCrop(storage, { ...display, x0: -1 })).toBe(false);
    expect(storage.setItem).toHaveBeenCalledTimes(1);
  });
});
