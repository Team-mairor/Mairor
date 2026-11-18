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

  it("모든 프레임이 같은 크기·칸 배치를 쓴다", () => {
    for (const option of PHOTO_FRAME_OPTIONS) {
      expect(option.template.output.width).toBe(BASIC_PHOTO_FRAME.output.width);
      expect(option.template.output.height).toBe(BASIC_PHOTO_FRAME.output.height);
      expect(option.template.slots).toEqual(BASIC_PHOTO_FRAME.slots);
    }
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
    expect(findPhotoFrameOption("nope")).toBeUndefined();
    expect(findPhotoFrameOption(null)).toBeUndefined();
  });
});
