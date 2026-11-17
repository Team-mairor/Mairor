import { describe, expect, it } from "vitest";

import { GRID, MEASURED } from "@/domain/gauge/spec";

import { maxZone, zoneCovers } from "./zones";

/** 칸 번호가 조건을 만족하는 칸만 1로 채운 가린 몫 표 */
const cover = (rule: (row: number, col: number) => boolean) => {
  const out = new Float32Array(GRID * GRID);
  for (let k = 0; k < out.length; k++) out[k] = rule(Math.floor(k / GRID), k % GRID) ? 1 : 0;
  return out;
};

describe("구역별 가린 몫", () => {
  it("가림이 없으면 모두 0이다", () => {
    const z = zoneCovers(cover(() => false));
    expect(z).toEqual({ whole: 0, left: 0, right: 0, upper: 0, lower: 0 });
    expect(maxZone(z)).toBe(0);
  });

  it("모두 가리면 모두 1이다", () => {
    const z = zoneCovers(cover(() => true));
    expect(z).toEqual({ whole: 1, left: 1, right: 1, upper: 1, lower: 1 });
  });

  it("왼쪽 반만 가리면 왼쪽 1, 오른쪽 0이고 전체는 그 사이다", () => {
    const z = zoneCovers(cover((_row, col) => col < GRID / 2));
    expect(z.left).toBe(1);
    expect(z.right).toBe(0);
    expect(z.whole).toBeGreaterThan(0.3);
    expect(z.whole).toBeLessThan(0.7);
    expect(maxZone(z)).toBe(1);
  });

  it("재지 않는 칸(눈 구멍 등)은 세지 않는다", () => {
    const unmeasured = [...MEASURED].findIndex((v) => v === 0);
    expect(unmeasured).toBeGreaterThanOrEqual(0);
    const all = new Float32Array(GRID * GRID).fill(1);
    all[unmeasured] = 0;
    // 재지 않는 칸만 0이므로 모든 구역이 그대로 1이다
    expect(zoneCovers(all).whole).toBe(1);
  });
});
