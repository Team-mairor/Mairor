import { faceBox, faceWidthRatio, type FaceFrame } from "@/features/face";

import type { Pixels } from "./cells";
import type { FrameState } from "./stability";

/** 눈마다 점 6개(눈꼬리 · 위 두 점 · 눈앞머리 · 아래 두 점). AI area_preparation과 같다 */
const EYE_OPEN_POINTS = [
  [33, 160, 158, 133, 153, 144],
  [362, 385, 387, 263, 373, 380],
] as const;

/** 얼굴 상자 가운데만 보도록 네 변에서 줄이는 몫. 얼굴 등록 밝기와 같다 */
const BRIGHTNESS_INSET = 0.25;

/**
 * 눈마다 (세로 길이 두 개의 평균) ÷ 가로 길이를 사진 픽셀로 재고 작은 쪽을 쓴다(AI eye_openness).
 * 눈 모양에 따라 뜬 눈도 0.12~0.2로 읽혀 판정에는 쓰지 않고 디버그에 띄운다
 */
export function eyeAspect(frame: FaceFrame): number {
  const { width, height } = frame.imageSize;
  const at = (i: number) => {
    const p = frame.landmarks[i];
    return [p.x * width, p.y * height] as const;
  };
  const dist = (i: number, j: number) => {
    const [ax, ay] = at(i);
    const [bx, by] = at(j);
    return Math.hypot(ax - bx, ay - by);
  };
  return Math.min(
    ...EYE_OPEN_POINTS.map(
      ([o, t1, t2, i, b2, b1]) => (dist(t1, b1) + dist(t2, b2)) / (2 * dist(o, i)),
    ),
  );
}

/** 눈 뜬 정도(0 감음 ~ 1 뜸, 덜 뜬 쪽). 깜빡임 값으로 재 사람마다 눈 모양 차이가 적다 */
export const eyesOpen = (frame: FaceFrame) =>
  Math.min(frame.eyes.left.openness, frame.eyes.right.openness);

/** 얼굴 상자 가운데의 평균 밝기(0~255). 얼굴 등록 밝기와 같은 식이다 */
export function faceBrightness(frame: FaceFrame, pixels: Pixels): number | null {
  const { minX, maxX, minY, maxY } = faceBox(frame);
  const dx = (maxX - minX) * BRIGHTNESS_INSET;
  const dy = (maxY - minY) * BRIGHTNESS_INSET;
  const x0 = Math.max(0, Math.floor((minX + dx) * pixels.width));
  const x1 = Math.min(pixels.width, Math.ceil((maxX - dx) * pixels.width));
  const y0 = Math.max(0, Math.floor((minY + dy) * pixels.height));
  const y1 = Math.min(pixels.height, Math.ceil((maxY - dy) * pixels.height));
  if (x1 - x0 < 1 || y1 - y0 < 1) return null;
  let sum = 0;
  let n = 0;
  for (let y = y0; y < y1; y += 2)
    for (let x = x0; x < x1; x += 2) {
      const i = (y * pixels.width + x) * 4;
      sum += 0.299 * pixels.data[i] + 0.587 * pixels.data[i + 1] + 0.114 * pixels.data[i + 2];
      n++;
    }
  return n ? sum / n : null;
}

/** 측정 불가 판정에 넣을 사진 상태. 맨피부 흔들림은 칸 색을 읽은 뒤에 채우고, 가린 몫(covered)은 아직 재지 않는다 */
export function frameState(frame: FaceFrame | null, pixels: Pixels | null): FrameState {
  if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold")
    return { faces: 0 };
  return {
    faces: 1,
    ...frame.pose,
    eyes: eyesOpen(frame),
    faceWidth: faceWidthRatio(frame),
    brightness: pixels ? faceBrightness(frame, pixels) : null,
  };
}
