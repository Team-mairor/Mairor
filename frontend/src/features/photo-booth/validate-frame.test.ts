import { describe, expect, it } from "vitest";

import { BASIC_PHOTO_FRAME, type PhotoFrameTemplate, type PhotoSlot } from "./frame";
import { assertPhotoFrame } from "./validate-frame";

function changedSlot(patch: Partial<PhotoSlot>): PhotoFrameTemplate {
  return {
    ...BASIC_PHOTO_FRAME,
    slots: [
      { ...BASIC_PHOTO_FRAME.slots[0], ...patch },
      BASIC_PHOTO_FRAME.slots[1],
      BASIC_PHOTO_FRAME.slots[2],
      BASIC_PHOTO_FRAME.slots[3],
    ],
  };
}

describe("네컷 프레임 규격", () => {
  it("기본 프레임과 로컬 디자인 이미지 경로를 허용한다", () => {
    expect(() => assertPhotoFrame(BASIC_PHOTO_FRAME)).not.toThrow();
    expect(() =>
      assertPhotoFrame({ ...BASIC_PHOTO_FRAME, overlaySrc: "/images/photo/frame.png" }),
    ).not.toThrow();
  });

  it.each([0, -1, 1.5, NaN, Infinity])("잘못된 출력 크기·버전 %s를 거부한다", (value) => {
    expect(() => assertPhotoFrame({ ...BASIC_PHOTO_FRAME, version: value })).toThrow(RangeError);
    for (const dimension of ["width", "height"] as const) {
      expect(() =>
        assertPhotoFrame({
          ...BASIC_PHOTO_FRAME,
          output: { ...BASIC_PHOTO_FRAME.output, [dimension]: value },
        }),
      ).toThrow(RangeError);
    }
  });

  it("빈 프레임 ID를 거부한다", () => {
    expect(() => assertPhotoFrame({ ...BASIC_PHOTO_FRAME, id: " " })).toThrow(RangeError);
  });

  it.each(["transparent", "#ffffff00", "#fff", "red"])(
    "불투명 HEX 계약 밖 배경 %s를 거부한다",
    (background) => {
      expect(() =>
        assertPhotoFrame({
          ...BASIC_PHOTO_FRAME,
          output: { ...BASIC_PHOTO_FRAME.output, background },
        }),
      ).toThrow(RangeError);
    },
  );

  it.each([
    "https://example.com/frame.png",
    "//example.com/frame.png",
    "images/frame.png",
    "/\\frame.png",
    "",
  ])("원격·상대·잘못된 이미지 경로 %s를 거부한다", (overlaySrc) => {
    expect(() => assertPhotoFrame({ ...BASIC_PHOTO_FRAME, overlaySrc })).toThrow(RangeError);
  });

  it("사진 칸이 누락된 템플릿을 거부한다", () => {
    const slots = BASIC_PHOTO_FRAME.slots.slice(0, 3);
    // 외부에서 타입 검증 없이 넘어온 잘못된 개수도 런타임에서 검출한다.
    expect(() =>
      assertPhotoFrame({ ...BASIC_PHOTO_FRAME, slots } as unknown as PhotoFrameTemplate),
    ).toThrow(RangeError);
  });

  it("중복되거나 순서가 바뀐 슬롯 ID를 거부한다", () => {
    expect(() => assertPhotoFrame(changedSlot({ id: "slot-2" }))).toThrow(RangeError);
  });

  it.each([{ x: -1 }, { y: 0.5 }, { width: 0 }, { height: Infinity }, { x: 1000 }, { y: 1700 }])(
    "잘못된 슬롯 좌표·크기 %j를 거부한다",
    (patch) => {
      expect(() => assertPhotoFrame(changedSlot(patch))).toThrow(RangeError);
    },
  );

  it("사진 영역의 겹침은 거부하고 경계가 맞닿는 배치는 허용한다", () => {
    expect(() => assertPhotoFrame(changedSlot({ width: 883 }))).toThrow(RangeError);
    expect(() => assertPhotoFrame(changedSlot({ width: 882 }))).not.toThrow();
    expect(() => assertPhotoFrame(changedSlot({ height: 1146 }))).toThrow(RangeError);
    expect(() => assertPhotoFrame(changedSlot({ height: 1145 }))).not.toThrow();
  });

  it("영역이 출력 우측·하단 경계에 정확히 닿는 것은 허용한다", () => {
    expect(() =>
      assertPhotoFrame({
        ...BASIC_PHOTO_FRAME,
        output: { ...BASIC_PHOTO_FRAME.output, width: 1755, height: 2516 },
        brand: undefined,
      }),
    ).not.toThrow();
  });
});
