import { IMAGENET_MEAN, IMAGENET_STD, OCCLUSION_CROP_SCALE } from "./constants";

export interface Point {
  x: number;
  y: number;
}

export interface CropBox {
  left: number;
  top: number;
  side: number;
}

/**
 * 얼굴 점(0~1 × 사진 가로 · 세로)을 감싼 네모의 긴 변 × 배율이 한 변인 정사각형을 낸다.
 * 가운데는 네모 가운데이고 왼쪽 위 · 한 변은 반올림한다. 사진 밖은 그리는 쪽에서 검정(0)으로 둔다
 */
export function squareCropBox(
  points: readonly Point[],
  width: number,
  height: number,
  scale = OCCLUSION_CROP_SCALE,
): CropBox {
  if (points.length === 0) throw new Error("얼굴 점이 없습니다");
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const p of points) {
    minX = Math.min(minX, p.x * width);
    maxX = Math.max(maxX, p.x * width);
    minY = Math.min(minY, p.y * height);
    maxY = Math.max(maxY, p.y * height);
  }
  const side = Math.max(maxX - minX, maxY - minY) * scale;
  return {
    left: Math.round((minX + maxX) / 2 - side / 2),
    top: Math.round((minY + maxY) / 2 - side / 2),
    side: Math.round(side),
  };
}

/** size × size RGBA 사진을 RGB ÷ 255 → (값 − 평균) ÷ 표준편차로 바꾼 채널 먼저(1, 3, S, S) 순서의 float32로 만든다 */
export function toModelInput(rgba: Uint8ClampedArray, size: number): Float32Array {
  const pixels = size * size;
  if (rgba.length !== pixels * 4) throw new Error("사진 크기가 입력 크기와 맞지 않습니다");
  const out = new Float32Array(pixels * 3);
  for (let i = 0; i < pixels; i++) {
    for (let c = 0; c < 3; c++) {
      out[c * pixels + i] = (rgba[i * 4 + c] / 255 - IMAGENET_MEAN[c]) / IMAGENET_STD[c];
    }
  }
  return out;
}
