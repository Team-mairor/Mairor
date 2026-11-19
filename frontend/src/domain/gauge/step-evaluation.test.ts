import { describe, expect, it } from "vitest";

import type { GaugeReference } from "@/vision/guide";

import type { Baseline } from "./baseline";
import { linearOfSrgb, type Vec3 } from "./measure";
import { GRID, MEASURED } from "./spec";
import { evaluateStep, SIDES, THRESHOLDS } from "./step-evaluation";
import spec from "../../../../shared/gauge/step_evaluation.v1.json" with { type: "json" };

type Case = (typeof spec.cases)[number];

/** [행, 시작 열, 끝 열(포함)] 목록을 칸 표로 */
function cellsOf(runs: readonly (readonly number[])[] | undefined): Uint8Array {
  const out = new Uint8Array(GRID * GRID);
  for (const [row, from, to] of runs ?? [])
    for (let c = from; c <= to; c++) out[row * GRID + c] = 1;
  return out;
}

const hexRgb = (hex: string): Vec3 =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as Vec3;

function gaugeOf(reference: Case["reference"]): GaugeReference | null {
  if (!reference) return null;
  return {
    color: { hex: "#000000", lab: reference.lab as Vec3 },
    effect: { delta: reference.delta as Vec3, size: 1, direction: "darker" },
    strength: 0,
    reason: null,
    white: { hex: reference.white, lab: [0, 0, 0] },
  };
}

/** 시작은 잴 칸이 모두 맨피부 색, 끝은 거기에 조명 · 바른 색을 더하고 가린 칸을 비운 것 */
function baselines(c: Case): { start: Baseline | null; end: Baseline } {
  const lab = new Float32Array(GRID * GRID * 3).fill(NaN);
  for (let k = 0; k < GRID * GRID; k++) if (MEASURED[k]) lab.set(spec.skin as number[], k * 3);
  const start: Baseline = { lab, cells: MEASURED.slice(), frames: 15 };
  const endLab = Float32Array.from(lab);
  const light = ("light" in c ? c.light : [0, 0, 0]) as number[];
  for (let k = 0; k < GRID * GRID; k++)
    if (MEASURED[k]) for (let ch = 0; ch < 3; ch++) endLab[k * 3 + ch] += light[ch];
  for (const paint of c.paint) {
    const cells = cellsOf(paint.cells);
    for (let k = 0; k < GRID * GRID; k++)
      if (cells[k] && MEASURED[k])
        for (let ch = 0; ch < 3; ch++) endLab[k * 3 + ch] += paint.delta[ch];
  }
  const covered = cellsOf("covered" in c ? c.covered : []);
  const endCells = new Uint8Array(GRID * GRID);
  for (let k = 0; k < GRID * GRID; k++) {
    if (covered[k]) endLab.fill(NaN, k * 3, k * 3 + 3);
    endCells[k] = MEASURED[k] && !covered[k] ? 1 : 0;
  }
  return {
    start: "noStart" in c && c.noStart ? null : start,
    end: { lab: endLab, cells: endCells, frames: 15 },
  };
}

const closeOrNull = (actual: number | null, expected: number | null) => {
  if (expected === null) expect(actual).toBeNull();
  else expect(actual).toBeCloseTo(expected, 4);
};

describe("단계 끝 평가는 AI 기대값과 같다", () => {
  for (const c of spec.cases) {
    it(c.name, () => {
      const { start, end } = baselines(c);
      const result = evaluateStep({
        subStepId: c.name,
        makeup: c.makeup,
        start,
        end,
        areas: c.areas.map((a) => ({ region: a.region, cells: cellsOf(a.cells) })),
        gauge: gaugeOf(c.reference),
        white: "userWhite" in c && c.userWhite ? linearOfSrgb(hexRgb(c.userWhite)) : null,
      });
      const expected = c.expected;
      expect(result.reason).toBe(expected.reason);
      expect(result.ratioReason).toBe(expected.ratioReason);
      closeOrNull(result.coverage, expected.coverage);
      closeOrNull(result.overflow, expected.overflow);
      closeOrNull(result.ratio, expected.ratio);
      closeOrNull(result.drift, expected.drift);
      for (const side of SIDES) {
        closeOrNull(result.sides[side].coverage, expected.sides[side].coverage);
        closeOrNull(result.sides[side].overflow, expected.sides[side].overflow);
      }
      expect(result.regions).toHaveLength(expected.regions.length);
      expected.regions.forEach((region, i) => {
        expect(result.regions[i].region).toBe(region.region);
        expect(result.regions[i].reason).toBe(region.reason);
        expect(result.regions[i].cells).toBe(region.cells);
        expect(result.regions[i].band).toBe(region.band);
        closeOrNull(result.regions[i].coverage, region.coverage);
        closeOrNull(result.regions[i].overflow, region.overflow);
      });
    });
  }

  it("안내 문장 기준값을 공유 규격에서 읽는다", () => {
    expect(THRESHOLDS).toEqual(spec.thresholds);
  });
});
