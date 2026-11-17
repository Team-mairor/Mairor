import type { FaceFrame, NormalizedRect, Point, ViewTransform } from "@/vision/face";

import type { GuideStep } from "./types";

export const TABLET_WIDTH = 800;
export const TABLET_HEIGHT = 1200;
export const TUTORIAL_TOP = 140;
export const TUTORIAL_BOTTOM = 372;
export const CROP_KEY = "mairor:tutorial-crop:v1";
const BASE_AREA_HEIGHT = TABLET_HEIGHT - TUTORIAL_TOP - TUTORIAL_BOTTOM;

/** globals.css의 PC 칸(800×1280) 조건 */
export const PC_FRAME_QUERY = "(orientation: landscape) and (pointer: fine)";

/**
 * 앱 화면의 레이아웃 높이. globals.css의 zoom(min(1, 폭/800, 높이/1200))을 되돌린 값이다.
 * 주소창 있는 크롬은 1200, 전체 화면(800×1280)과 PC 칸은 1280이다
 */
export function layoutHeight(viewport: { width: number; height: number }, pcFrame = false): number {
  if (pcFrame) return 1280;
  const zoom = Math.min(1, viewport.width / TABLET_WIDTH, viewport.height / TABLET_HEIGHT);
  return viewport.height / zoom;
}

/** 레이아웃 높이에서 tutorial이 위·아래를 비우고 영상에 쓰는 높이 */
export const tutorialAreaHeight = (height: number) => height - TUTORIAL_TOP - TUTORIAL_BOTTOM;

export function tutorialVideoRatio(
  video: Pick<HTMLVideoElement, "videoWidth" | "videoHeight" | "readyState"> | null,
): number | null {
  return video && video.readyState >= 1 && video.videoWidth > 0 && video.videoHeight > 0
    ? video.videoWidth / video.videoHeight
    : null;
}

const cropHeightRatio = (imageRatio: number, areaHeight: number) =>
  (imageRatio * areaHeight) / TABLET_WIDTH;

export function centeredTutorialCrop(
  imageRatio: number,
  areaHeight = BASE_AREA_HEIGHT,
): NormalizedRect {
  const factor = cropHeightRatio(imageRatio, areaHeight);
  const width = Math.min(0.9, 0.9 / factor);
  const height = width * factor;
  return { x0: (1 - width) / 2, y0: (1 - height) / 2, x1: (1 + width) / 2, y1: (1 + height) / 2 };
}

export function resizeTutorialCrop(
  rect: NormalizedRect,
  width: number,
  imageRatio: number,
  areaHeight = BASE_AREA_HEIGHT,
): NormalizedRect {
  const factor = cropHeightRatio(imageRatio, areaHeight);
  const min = Math.max(0.06, 0.06 / factor);
  const max = Math.min(1 - rect.x0, (1 - rect.y0) / factor);
  if (max < min) return rect;
  const size = Math.max(min, Math.min(width, max));
  return { ...rect, x1: rect.x0 + size, y1: rect.y0 + size * factor };
}

/** 거울 방향으로 표시한 원본 영상의 비율 좌표. */
export function validCrop(value: unknown): value is NormalizedRect {
  if (!value || typeof value !== "object") return false;
  const r = value as NormalizedRect;
  return (
    [r.x0, r.y0, r.x1, r.y1].every(Number.isFinite) &&
    r.x0 >= 0 &&
    r.y0 >= 0 &&
    r.x1 <= 1 &&
    r.y1 <= 1 &&
    r.x1 - r.x0 >= 0.05 &&
    r.y1 - r.y0 >= 0.05
  );
}

export function cropTransform(
  image: { width: number; height: number },
  target: { width: number; height: number },
  crop: NormalizedRect,
): ViewTransform {
  const width = (crop.x1 - crop.x0) * image.width;
  const height = (crop.y1 - crop.y0) * image.height;
  const scale = Math.min(target.width / width, target.height / height);
  return {
    mirrored: true,
    scale,
    offsetX: (target.width - width * scale) / 2 - crop.x0 * image.width * scale,
    offsetY: (target.height - height * scale) / 2 - crop.y0 * image.height * scale,
  };
}

/** 크롭 좌표는 거울 방향이다. 인식 좌표는 그대로 두고 표시 부위만 판정한다. */
export function isStepInCrop(
  step: Pick<GuideStep, "regions"> | null,
  frame: FaceFrame,
  crop: NormalizedRect,
  recoverRatio = 0,
): boolean {
  const regions = step?.regions.length ? step.regions : ["faceOval" as const];
  const area = (points: Point[]) =>
    Math.abs(
      points.reduce((sum, p, i) => {
        const next = points[(i + 1) % points.length];
        return sum + p.x * next.y - next.x * p.y;
      }, 0),
    ) / 2;
  // 고개 돌림은 부위 표시 진하기(guideRegionAlpha)가 숨기므로 여기서는 크롭과 겹치는지만 본다
  return regions.some((name) => {
    const points = frame.regions[name].indices.map((i) => ({
      x: 1 - frame.landmarks[i].x,
      y: frame.landmarks[i].y,
    }));
    const original = area(points);
    let clipped = points;
    for (const [axis, edge, lower] of [
      ["x", crop.x0, true],
      ["x", crop.x1, false],
      ["y", crop.y0, true],
      ["y", crop.y1, false],
    ] as const) {
      const input = clipped;
      clipped = [];
      const inside = (p: Point) => (lower ? p[axis] >= edge : p[axis] <= edge);
      input.forEach((p, i) => {
        const prev = input[(i + input.length - 1) % input.length];
        if (inside(p) !== inside(prev)) {
          const t = (edge - prev[axis]) / (p[axis] - prev[axis]);
          clipped.push({ x: prev.x + (p.x - prev.x) * t, y: prev.y + (p.y - prev.y) * t });
        }
        if (inside(p)) clipped.push(p);
      });
    }
    return original > 0 && area(clipped) > original * recoverRatio;
  });
}

export function tabletPreviewScale(
  screen: { width: number; height: number },
  height = TABLET_HEIGHT,
): number {
  return Math.max(
    0,
    Math.min(1, (screen.width - 32) / TABLET_WIDTH, (screen.height - 32) / height),
  );
}

export function writeTutorialCrop(
  storage: Pick<Storage, "setItem" | "removeItem">,
  value: NormalizedRect | null,
): boolean {
  if (value && !validCrop(value)) return false;
  try {
    if (value) storage.setItem(CROP_KEY, JSON.stringify(value));
    else storage.removeItem(CROP_KEY);
    return true;
  } catch {
    return false;
  }
}
