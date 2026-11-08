import { describe, expect, it } from "vitest";

import { formatAgo, formatDuration, formatViews } from "./video";

describe("영상 표시값", () => {
  it("길이는 한 시간이 넘으면 시를 붙인다", () => {
    expect(formatDuration(760)).toBe("12:40");
    expect(formatDuration(5)).toBe("0:05");
    expect(formatDuration(3723)).toBe("1:02:03");
  });

  it("조회수는 만·억 단위로 줄이고 10 미만만 소수 한 자리", () => {
    expect(formatViews(950)).toBe("950회");
    expect(formatViews(32_500)).toBe("3.2만회");
    expect(formatViews(180_345)).toBe("18만회");
    expect(formatViews(150_000_000)).toBe("1.5억회");
  });

  it("게시 시각은 가장 큰 단위로", () => {
    const now = Date.parse("2026-11-06T00:00:00Z");
    expect(formatAgo("2026-10-23T00:00:00Z", now)).toBe("2주 전");
    expect(formatAgo("2026-11-05T23:59:30Z", now)).toBe("방금");
  });
});
