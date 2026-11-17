import { describe, expect, it } from "vitest";

import { calculatePhotoCaptureCrop } from "./capture-crop";
import { BASIC_PHOTO_FRAME } from "./frame";

describe("네 컷 촬영 크롭", () => {
  it("슬롯 비율을 유지하면서 반 픽셀 오프셋을 정수 좌표로 내린다", () => {
    const crop = calculatePhotoCaptureCrop(
      { width: 1280, height: 720 },
      { width: 520, height: 760 },
    );

    expect(crop).toEqual({ x: 399, y: 8, width: 481, height: 703 });
    expect(Number.isInteger(crop.x)).toBe(true);
    expect(Number.isInteger(crop.y)).toBe(true);
  });

  it.each([
    [1920, 1080],
    [1280, 720],
    [640, 480],
  ])("실제 프레임 칸은 %i×%i 카메라 높이를 거의 다 쓴다(확대되지 않는다)", (width, height) => {
    for (const slot of BASIC_PHOTO_FRAME.slots) {
      const crop = calculatePhotoCaptureCrop({ width, height }, slot);
      expect(crop.height).toBeGreaterThanOrEqual(height * 0.99);
    }
  });
});
