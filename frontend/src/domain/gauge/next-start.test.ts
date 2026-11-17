import { describe, expect, it } from "vitest";

import { nextStartBaseline, trimTail, type TailShot } from "./next-start";
import { GRID, MEASURED } from "./spec";
import type { FrameState } from "./stability";

const first = [...MEASURED.keys()].find((k) => MEASURED[k])!;
const grid = (l: number) => {
  const g = new Float32Array(GRID * GRID * 3).fill(NaN);
  for (let k = 0; k < GRID * GRID; k++) if (MEASURED[k]) g.set([l, 10, 20], k * 3);
  return g;
};
const shot = (at: number, l: number, state: Partial<FrameState> = {}): TailShot => ({
  at,
  state: { faces: 1, ...state },
  grid: grid(l),
});

describe("묶음 둘째 단계 시작 기준", () => {
  it("「다음」 직전 2초 안의 쓸 수 있는 사진으로 칸마다 가운데 값을 낸다", () => {
    const tail = [shot(0, 90), shot(1200, 60), shot(1600, 62), shot(2000, 64), shot(2800, 61)];
    const base = nextStartBaseline(tail, "lip", 3000, 0);
    expect(base?.frames).toBe(4);
    expect(base?.lab[first * 3]).toBeCloseTo(61.5, 5);
  });

  it("다음 단계 화장 종류로 다시 걸러, 눈 화장 단계면 눈 감은 사진을 뺀다", () => {
    const tail = [
      shot(1200, 60),
      shot(1600, 62, { eyes: 0.1 }),
      shot(2000, 64, { eyes: 0.1 }),
      shot(2800, 61),
    ];
    expect(nextStartBaseline(tail, "lip", 3000, 0)?.frames).toBe(4);
    expect(nextStartBaseline(tail, "eyeshadow", 3000, 0)).toBeNull();
  });

  it("앞 단계 기준과 견준 조명 바뀜은 다음 단계 기준을 고를 때 보지 않는다", () => {
    const tail = [1200, 1600, 2000].map((at) => shot(at, 60, { drift: 99 }));
    expect(nextStartBaseline(tail, "lip", 2500, 0)?.frames).toBe(3);
  });

  it("쓸 수 있는 사진이 3장보다 적으면 null이라 준비 카드에서 따로 모은다", () => {
    const tail = [shot(1500, 60), shot(2000, 60, { faces: 0 }), shot(2500, 60)];
    expect(nextStartBaseline(tail, "lip", 3000, 0)).toBeNull();
  });

  it("그 사람 정면 pitch 둘레 사진만 쓴다", () => {
    const tail = [
      shot(1200, 60, { pitch: -0.3 }),
      shot(1600, 62, { pitch: -0.2 }),
      shot(2000, 64, { pitch: -0.1 }),
      shot(2400, 66, { pitch: 0.05 }),
    ];
    const base = nextStartBaseline(tail, "lip", 3000, -0.23);
    expect(base?.frames).toBe(3);
    expect(base?.lab[first * 3]).toBeCloseTo(62, 5);
  });

  it("그 사람 정면을 아직 못 정했으면 준비 카드로 넘긴다", () => {
    const tail = [shot(1200, 60), shot(1600, 62), shot(2000, 64)];
    expect(nextStartBaseline(tail, "lip", 2500, null)).toBeNull();
  });

  it("남겨 둔 사진은 2초가 지나면 버린다", () => {
    const tail = [shot(0, 60), shot(1500, 60), shot(2500, 60)];
    expect(trimTail(tail, 3000).map((s) => s.at)).toEqual([1500, 2500]);
  });
});
