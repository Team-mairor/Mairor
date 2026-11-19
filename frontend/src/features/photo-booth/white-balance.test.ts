import { describe, expect, it } from "vitest";

import { estimateSkinGains, gainsToMatrix, NEUTRAL_GAINS, smoothGains } from "./white-balance";

function solid(r: number, g: number, b: number, pixels = 100) {
  const data = new Uint8ClampedArray(pixels * 4);
  for (let i = 0; i < pixels; i += 1) data.set([r, g, b, 255], i * 4);
  return data;
}

const apply = (gains: { b: number }, [r, g, b]: number[]) => [r, g, Math.min(255, b * gains.b)];

describe("estimateSkinGains", () => {
  it("노란 조명의 피부는 파랑을 올려 목표 비율로 옮긴다", () => {
    const gains = estimateSkinGains(solid(205, 168, 118))!;
    expect(gains.b).toBeGreaterThan(1.1);
    const [r, , b] = apply(gains, [205, 168, 118]);
    expect(b / r).toBeCloseTo(0.66, 2);
  });

  it("노랗지 않은 피부도 같은 목표로 모아 결과가 비슷하다", () => {
    const warm = apply(estimateSkinGains(solid(205, 168, 118))!, [205, 168, 118]);
    const neutral = apply(estimateSkinGains(solid(224, 182, 152))!, [224, 182, 152]);
    expect(warm[2] / warm[0]).toBeCloseTo(neutral[2] / neutral[0], 2);
  });

  it("피부색이 거의 없는 장면은 null을 돌려 준다", () => {
    expect(estimateSkinGains(solid(20, 20, 20))).toBeNull();
    expect(estimateSkinGains(solid(120, 160, 90))).toBeNull();
    expect(estimateSkinGains(new Uint8ClampedArray(0))).toBeNull();
  });

  it("배율은 정해 둔 범위를 넘지 않는다", () => {
    const gains = estimateSkinGains(solid(230, 160, 85))!;
    expect(gains.b).toBe(1.5);
  });
});

describe("smoothGains", () => {
  it("이전 값에서 비율만큼만 옮긴다", () => {
    const next = smoothGains(NEUTRAL_GAINS, { b: 1.4 }, 0.25);
    expect(next.b).toBeCloseTo(1.1);
  });
});

describe("gainsToMatrix", () => {
  it("파랑에만 배율을 넣는다", () => {
    expect(gainsToMatrix({ b: 1.25 })).toBe("1 0 0 0 0  0 1 0 0 0  0 0 1.2500 0 0  0 0 0 1 0");
  });
});
