import { describe, expect, it } from "vitest";

import type { Baseline } from "./baseline";
import { drift, grow, lightChange, makeupEffect } from "./light";
import fixture from "./light.fixture.json" with { type: "json" };
import { GRID, MEASURED, SKIN } from "./spec";

/** scripts/gauge-light-fixture.py와 같은 입력 */
function scene() {
  const lab = new Float32Array(GRID * GRID * 3).fill(NaN);
  const current = new Float32Array(GRID * GRID * 3).fill(NaN);
  const made = new Uint8Array(GRID * GRID);
  for (let i = 0; i < GRID; i++)
    for (let j = 0; j < GRID; j++) {
      const k = i * GRID + j;
      if (i >= 70 && i <= 80 && j >= 40 && j <= 60) made[k] = 1;
      if (!MEASURED[k]) continue;
      const base = [
        60 + 5 * Math.sin(i / 9) + 3 * Math.cos(j / 11),
        12 + 2 * Math.sin(j / 7),
        18 + 2 * Math.cos(i / 13),
      ].map(Math.fround);
      const change = [-4 - 3 * (j / (GRID - 1)), 1.5 * Math.sin(i / 20), 2 * Math.cos(j / 17)].map(
        Math.fround,
      );
      lab.set(base, k * 3);
      current.set(
        base.map((v, ch) => v + change[ch]),
        k * 3,
      );
      if (made[k]) {
        current[k * 3] -= 10;
        current[k * 3 + 1] += 6;
      }
    }
  const base: Baseline = { lab, cells: MEASURED, frames: 15 };
  return { base, current, made };
}

describe("조명 보정", () => {
  it("바르는 칸 둘레를 OpenCV 타원 dilate와 같게 넓힌다", () => {
    const { made } = scene();
    expect(grow(made).reduce((a, b) => a + b, 0)).toBe(fixture.grownCount);
  });

  it("칸마다 조명 변화가 AI(OpenCV GaussianBlur, 반사 가장자리)와 같다", () => {
    const { base, current, made } = scene();
    const light = lightChange(current, base, made);
    for (const [key, expected] of Object.entries(fixture.light)) {
      const k = Number(key);
      expected.forEach((v, ch) => expect(light[k * 3 + ch]).toBeCloseTo(v, 3));
    }
  });

  it("고르게 바뀐 조명은 안 바른 칸에서 빠지고, 바른 칸에는 화장만 남는다", () => {
    const { base, current, made } = scene();
    const effect = makeupEffect(current, base, made);
    // 바른 칸 가운데는 조명 재기에서 빠져 화장 효과(L −10, a +6)가 거의 그대로 남는다
    const center = 75 * GRID + 50;
    expect(effect[center * 3]).toBeCloseTo(-10, 0);
    expect(effect[center * 3 + 1]).toBeCloseTo(6, 0);
    // 바르는 곳에서 먼 맨피부 칸은 0 가까이로 돌아온다
    const far = [...SKIN.keys()].find((k) => SKIN[k] && MEASURED[k] && Math.floor(k / GRID) < 40)!;
    for (let ch = 0; ch < 3; ch++) expect(Math.abs(effect[far * 3 + ch])).toBeLessThan(0.5);
  });

  it("조명을 잴 맨피부가 없으면 조명 변화는 0이고 흔들림 크기는 모른다", () => {
    const { base, current } = scene();
    const all = new Uint8Array(GRID * GRID).fill(1);
    expect(lightChange(current, base, all).every((v) => v === 0)).toBe(true);
    expect(drift(current, base, all)).toMatchObject({ cells: 0, size: NaN });
  });

  it("카메라가 어두워지면 흔들림 밝기가 음수이고 크기가 0보다 크다", () => {
    const { base, current, made } = scene();
    const d = drift(current, base, made);
    expect(d.lightness).toBeLessThan(-4);
    expect(d.size).toBeGreaterThan(0);
    expect(d.cells).toBe(fixture.freeCount);
  });
});
