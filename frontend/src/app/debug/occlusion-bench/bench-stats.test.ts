import { describe, expect, it } from "vitest";

import { compareMasks, summarize } from "./bench-stats";

describe("가림 모델 벤치마크 통계", () => {
  it("최소 · 가운데 · 90% · 최대 · 평균을 낸다", () => {
    const s = summarize([10, 20, 30, 40, 50, 60, 70, 80, 90, 100]);
    expect(s).toEqual({ n: 10, min: 10, median: 55, p90: 90, max: 100, mean: 55 });
  });

  it("값이 홀수 개면 가운데 값을 그대로 쓴다", () => {
    expect(summarize([3, 1, 2])?.median).toBe(2);
  });

  it("비었으면 null이다", () => {
    expect(summarize([])).toBeNull();
  });

  it("두 가림 표의 같은 픽셀 비율과 겹침을 낸다", () => {
    const a = new Uint8Array([1, 1, 0, 0]);
    const b = new Uint8Array([1, 0, 0, 0]);
    expect(compareMasks(a, b)).toEqual({ samePixels: 0.75, iou: 0.5 });
  });

  it("둘 다 가림이 없으면 겹침은 null이다", () => {
    expect(compareMasks(new Uint8Array(4), new Uint8Array(4))).toEqual({
      samePixels: 1,
      iou: null,
    });
  });
});
