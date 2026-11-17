import { describe, expect, it } from "vitest";

import { squareCropBox, toModelInput } from "./preprocess";

describe("가림 모델 입력 만들기", () => {
  it("얼굴 점을 감싼 네모의 긴 변 × 1.4 정사각형을 네모 가운데에 맞춘다", () => {
    // 가로 1000 · 세로 500 사진, 점이 x 400~600(폭 200) · y 100~400(높이 300)
    const box = squareCropBox(
      [
        { x: 0.4, y: 0.2 },
        { x: 0.6, y: 0.8 },
      ],
      1000,
      500,
    );
    // 긴 변 300 × 1.4 = 420, 가운데 (500, 250) → 왼쪽 위 (290, 40)
    expect(box).toEqual({ left: 290, top: 40, side: 420 });
  });

  it("왼쪽 위와 한 변을 정수로 반올림한다", () => {
    const box = squareCropBox(
      [
        { x: 0.1, y: 0.1 },
        { x: 0.33, y: 0.45 },
      ],
      101,
      77,
    );
    expect(Number.isInteger(box.left)).toBe(true);
    expect(Number.isInteger(box.top)).toBe(true);
    expect(Number.isInteger(box.side)).toBe(true);
  });

  it("점이 없으면 오류다", () => {
    expect(() => squareCropBox([], 100, 100)).toThrow();
  });

  it("RGB를 평균 · 표준편차로 정규화해 채널이 먼저인 순서로 둔다", () => {
    // 2 × 2 사진: 첫 픽셀은 R만 255, 나머지는 0
    const rgba = new Uint8ClampedArray(16);
    rgba[0] = 255;
    const out = toModelInput(rgba, 2);
    expect(out).toHaveLength(12);
    expect(out[0]).toBeCloseTo((1 - 0.485) / 0.229, 5); // R 채널 첫 픽셀
    expect(out[1]).toBeCloseTo((0 - 0.485) / 0.229, 5); // R 채널 둘째 픽셀
    expect(out[4]).toBeCloseTo((0 - 0.456) / 0.224, 5); // G 채널 첫 픽셀
    expect(out[8]).toBeCloseTo((0 - 0.406) / 0.225, 5); // B 채널 첫 픽셀
  });

  it("사진 크기가 입력 크기와 다르면 오류다", () => {
    expect(() => toModelInput(new Uint8ClampedArray(12), 2)).toThrow();
  });
});
