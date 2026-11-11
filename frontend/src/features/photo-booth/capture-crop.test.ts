import { describe, expect, it } from "vitest";

import { calculatePhotoCaptureCrop } from "./capture-crop";

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
});
