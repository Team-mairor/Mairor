import { describe, expect, it } from "vitest";

import { rgbToLab } from "@/lib/color";

import { deltaE, grow, inside, sampleRegion } from "./region-color";

const square = (c: number, r: number) => [
  { x: c - r, y: c - r },
  { x: c + r, y: c - r },
  { x: c + r, y: c + r },
  { x: c - r, y: c + r },
];

/** 가운데 칸만 rgb 색인 size×size 영상 */
function image(size: number, inner: number[], outer: number[], box: [number, number]) {
  const data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const c = x >= box[0] && x < box[1] && y >= box[0] && y < box[1] ? inner : outer;
      data.set([...c, 255], (y * size + x) * 4);
    }
  }
  return { data, width: size, height: size };
}

describe("region-color", () => {
  it("다각형 안팎을 가른다", () => {
    expect(inside({ x: 5, y: 5 }, square(5, 2))).toBe(true);
    expect(inside({ x: 8, y: 5 }, square(5, 2))).toBe(false);
  });

  it("중심 기준으로 키운다", () => {
    expect(grow(square(5, 2), 2)[0]).toEqual({ x: 1, y: 1 });
  });

  it("안과 둘레 띠 색을 따로 잰다", () => {
    const lip = [200, 80, 90];
    const skin = [220, 180, 160];
    const s = sampleRegion(image(40, lip, skin, [15, 25]), square(20, 5), 1.6);
    expect(s).not.toBeNull();
    expect(deltaE(s!.inner, rgbToLab(200, 80, 90))).toBeLessThan(0.01);
    expect(deltaE(s!.band, rgbToLab(220, 180, 160))).toBeLessThan(0.01);
  });

  it("구멍과 반사광은 뺀다", () => {
    const img = image(40, [255, 255, 255], [100, 100, 100], [18, 22]);
    const s = sampleRegion(img, square(20, 5), 1.6, square(20, 1));
    expect(s!.inner.l).toBeCloseTo(rgbToLab(100, 100, 100).l, 5);
  });
});
