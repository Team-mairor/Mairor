import { describe, expect, it } from "vitest";

import { BASIC_PHOTO_FRAME } from "./frame";
import { findPhotoFrameOption, PHOTO_FRAME_OPTIONS } from "./frame-options";
import { assertPhotoFrame } from "./validate-frame";

describe("PHOTO_FRAME_OPTIONS", () => {
  it("모든 프레임이 규칙을 만족한다", () => {
    for (const option of PHOTO_FRAME_OPTIONS) {
      expect(() => assertPhotoFrame(option.template)).not.toThrow();
    }
  });

  it("프레임 ID가 겹치지 않는다", () => {
    const ids = PHOTO_FRAME_OPTIONS.map((option) => option.id);
    const templateIds = PHOTO_FRAME_OPTIONS.map((option) => option.template.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(templateIds).size).toBe(templateIds.length);
  });

  it("기존 세 프레임이 같은 크기·칸 배치를 쓴다", () => {
    for (const option of PHOTO_FRAME_OPTIONS.filter(({ id }) =>
      ["ssafy15", "white", "black"].includes(id),
    )) {
      expect(option.template.output.width).toBe(BASIC_PHOTO_FRAME.output.width);
      expect(option.template.output.height).toBe(BASIC_PHOTO_FRAME.output.height);
      expect(option.template.slots).toEqual(BASIC_PHOTO_FRAME.slots);
    }
  });

  it("반쪽 프레임 두 개가 같은 출력 크기·칸 배치를 쓴다", () => {
    const basic = findPhotoFrameOption("ssafy-basic-half")!;
    const minju = findPhotoFrameOption("minju-half")!;
    expect(basic.template.output).toEqual({
      width: 900,
      height: 2646,
      background: "#ffffff",
    });
    expect(minju.template.output).toEqual(basic.template.output);
    expect(minju.template.slots).toEqual(basic.template.slots);
  });

  it("민주네컷은 결과 프레임과 같은 순서·위치의 촬영 안내 이미지를 쓴다", () => {
    const minju = findPhotoFrameOption("minju-half")!;
    expect(minju.guestHoleWidth).toBe(800);
    expect(minju.guests).toEqual([
      { src: "/images/photo/minju-half-guest-1.png", side: "left", width: 464, height: 476 },
      { src: "/images/photo/minju-half-guest-2.png", side: "right", width: 502, height: 522 },
      { src: "/images/photo/minju-half-guest-3.png", side: "left", width: 460, height: 538 },
      { src: "/images/photo/minju-half-guest-4.png", side: "right", width: 468, height: 474 },
    ]);
  });

  it("안내 이미지는 네 컷 모두 있거나 아예 없다", () => {
    for (const option of PHOTO_FRAME_OPTIONS) {
      if (option.guests) {
        expect(option.guests).toHaveLength(4);
        expect(option.guestHoleWidth).toBeGreaterThan(0);
      }
    }
  });

  it("ID로 프레임을 찾고 모르는 ID는 undefined를 돌려준다", () => {
    expect(findPhotoFrameOption("white")?.name).toBe("화이트");
    expect(findPhotoFrameOption("ssafy-basic-half")?.name).toBe("SSAFY 기본");
    expect(findPhotoFrameOption("minju-half")?.name).toBe("민주네컷");
    expect(findPhotoFrameOption("nope")).toBeUndefined();
    expect(findPhotoFrameOption(null)).toBeUndefined();
  });
});
