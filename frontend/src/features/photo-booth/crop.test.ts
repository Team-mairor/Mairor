import { describe, expect, it } from "vitest";

import { calculatePhotoCrop } from "./crop";
import { BASIC_PHOTO_FRAME } from "./frame";

const landscape = { width: 1600, height: 900 };
const portraitSlot = { width: 400, height: 600 };

describe("네컷 사진 cover 크롭", () => {
  it("가로 사진의 가운데를 세로 슬롯 비율로 자른다", () => {
    expect(calculatePhotoCrop(landscape, portraitSlot)).toEqual({
      x: 500,
      y: 0,
      width: 600,
      height: 900,
      mirrored: false,
    });
  });

  it("세로 사진의 위아래를 가로 슬롯 비율로 자른다", () => {
    expect(calculatePhotoCrop({ width: 900, height: 1600 }, { width: 600, height: 400 })).toEqual({
      x: 0,
      y: 500,
      width: 900,
      height: 600,
      mirrored: false,
    });
  });

  it("오른쪽으로 사진을 움직이면 원본의 왼쪽 영역을 보여준다", () => {
    expect(calculatePhotoCrop(landscape, portraitSlot, { panX: 1 }).x).toBe(0);
    expect(calculatePhotoCrop(landscape, portraitSlot, { panX: -1 }).x).toBe(1000);
  });

  it("반전 상태에서도 사용자에게 보이는 이동 방향을 유지한다", () => {
    const result = calculatePhotoCrop(landscape, portraitSlot, { panX: 1, mirrored: true });
    expect(result.x).toBe(1000);
    expect(result.mirrored).toBe(true);
  });

  it("확대 후 위아래 이동에도 원본 경계를 지킨다", () => {
    const top = calculatePhotoCrop(landscape, portraitSlot, { zoom: 2, panY: 1 });
    const bottom = calculatePhotoCrop(landscape, portraitSlot, { zoom: 2, panY: -1 });
    expect(top.width).toBe(300);
    expect(top.height).toBe(450);
    expect(top.y).toBe(0);
    expect(bottom.y).toBe(450);
  });

  it("미리보기와 출력 슬롯의 크기가 달라도 같은 원본 영역을 사용한다", () => {
    const placement = { zoom: 1.5, panX: 0.3, panY: -0.2, mirrored: true };
    expect(calculatePhotoCrop(landscape, portraitSlot, placement)).toEqual(
      calculatePhotoCrop(landscape, { width: 200, height: 300 }, placement),
    );
  });

  it("유한한 범위 밖 편집 값은 안전한 범위로 제한한다", () => {
    expect(calculatePhotoCrop(landscape, portraitSlot, { zoom: 99, panX: 9, panY: -9 })).toEqual(
      calculatePhotoCrop(landscape, portraitSlot, { zoom: 4, panX: 1, panY: -1 }),
    );
    expect(calculatePhotoCrop(landscape, portraitSlot, { zoom: 0 })).toEqual(
      calculatePhotoCrop(landscape, portraitSlot),
    );
  });

  it("여러 사진 비율과 편집 경계에서 슬롯 비율을 유지하고 사진 밖을 읽지 않는다", () => {
    for (const image of [landscape, { width: 900, height: 1600 }, { width: 1000, height: 1000 }]) {
      for (const slot of BASIC_PHOTO_FRAME.slots) {
        for (const zoom of [1, 2, 4]) {
          for (const panX of [-1, 0, 1]) {
            for (const panY of [-1, 0, 1]) {
              for (const mirrored of [false, true]) {
                const crop = calculatePhotoCrop(image, slot, { zoom, panX, panY, mirrored });
                expect(crop.width / crop.height).toBeCloseTo(slot.width / slot.height);
                expect(crop.x).toBeGreaterThanOrEqual(0);
                expect(crop.y).toBeGreaterThanOrEqual(0);
                expect(crop.x + crop.width).toBeLessThanOrEqual(image.width + 1e-9);
                expect(crop.y + crop.height).toBeLessThanOrEqual(image.height + 1e-9);
              }
            }
          }
        }
      }
    }
  });

  it.each([0, -1, NaN, Infinity])("크기 %s를 거부한다", (value) => {
    expect(() => calculatePhotoCrop({ width: value, height: 900 }, portraitSlot)).toThrow(
      RangeError,
    );
    expect(() => calculatePhotoCrop(landscape, { width: 400, height: value })).toThrow(RangeError);
  });

  it.each([NaN, Infinity, -Infinity])("유한하지 않은 편집 값 %s를 거부한다", (value) => {
    for (const field of ["zoom", "panX", "panY"] as const) {
      expect(() => calculatePhotoCrop(landscape, portraitSlot, { [field]: value })).toThrow(
        RangeError,
      );
    }
  });
});
