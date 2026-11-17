import { describe, expect, it } from "vitest";

import {
  isTooDark,
  isTooDarkReleased,
  needsMore,
  TOO_DARK_BAR,
  TOO_DARK_RELEASE_BAR,
} from "./alerts";

const shown = (
  bar: number | null,
  label: "lighter" | "similar" | "darker" | null,
  stale = false,
) => ({
  bar,
  label,
  stale,
});

describe("게이지 알림 판정", () => {
  it("연해요일 때만 더 바르라고 묻는다", () => {
    expect(needsMore(shown(30, "lighter"))).toBe(true);
    expect(needsMore(shown(50, "similar"))).toBe(false);
    expect(needsMore(shown(80, "darker"))).toBe(false);
  });

  it("못 재거나 못 재는 동안 남은 값이면 묻지 않는다", () => {
    expect(needsMore(null)).toBe(false);
    expect(needsMore(shown(null, null))).toBe(false);
    expect(needsMore(shown(30, "lighter", true))).toBe(false);
  });

  it("막대가 경계 이상이면 너무 진하다고 본다", () => {
    expect(isTooDark(shown(TOO_DARK_BAR, "darker"))).toBe(true);
    expect(isTooDark(shown(TOO_DARK_BAR - 0.1, "darker"))).toBe(false);
    expect(isTooDark(shown(100, "darker"))).toBe(true);
  });

  it("못 재거나 마지막 값이 남은 것이면 너무 진하다고 보지 않는다", () => {
    expect(isTooDark(null)).toBe(false);
    expect(isTooDark(shown(null, null))).toBe(false);
    expect(isTooDark(shown(90, "darker", true))).toBe(false);
  });

  it("다시 알리려면 풀림 경계 아래로 내려와야 한다", () => {
    expect(isTooDarkReleased(shown(TOO_DARK_RELEASE_BAR - 0.1, "darker"))).toBe(true);
    expect(isTooDarkReleased(shown(TOO_DARK_RELEASE_BAR, "darker"))).toBe(false);
    expect(isTooDarkReleased(shown(65, "darker"))).toBe(false);
    expect(isTooDarkReleased(shown(null, null))).toBe(false);
  });
});
