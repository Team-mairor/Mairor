import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import type { FaceMesh } from "@/features/overlay";

import { cellSampler, readCells, type Pixels } from "./cells";
import { deltaE2000, rgbToLab } from "./color";
import { GRID, MEASURED } from "./spec";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const mesh: FaceMesh = {
  ...read("../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../shared/face-mesh/uv.v1.json"),
};
const sampler = cellSampler(mesh);
/** 얼굴 지도를 그대로 찍은 사진처럼, 점 위치를 UV와 같게 둔다 */
const landmarks = mesh.uv.map(([x, y]) => ({ x, y }));

/** 가로 절반을 기준으로 왼쪽(u < 0.5)과 오른쪽을 다른 색으로 칠한 사진 */
function photo(size: number, left: number[], right: number[]): Pixels {
  const data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++)
      data.set([...(x < size / 2 ? left : right), 255], (y * size + x) * 4);
  return { width: size, height: size, data };
}

describe("칸 색", () => {
  it("재는 칸마다 색을 내고, 눈 구멍처럼 재지 않는 칸은 비운다", () => {
    const lab = readCells(photo(512, [200, 150, 130], [200, 150, 130]), landmarks, sampler);
    const skin = rgbToLab(200, 150, 130);
    let filled = 0;
    for (let k = 0; k < GRID * GRID; k++) {
      if (!MEASURED[k]) {
        expect(Number.isNaN(lab[k * 3])).toBe(true);
        continue;
      }
      if (Number.isNaN(lab[k * 3])) continue;
      filled++;
      expect(lab[k * 3]).toBeCloseTo(skin[0], 3);
    }
    // 얼굴 메시 바깥으로 살짝 걸친 가장자리 칸 말고는 모두 색이 난다
    expect(filled / MEASURED.reduce((a, b) => a + b, 0)).toBeGreaterThan(0.97);
  });

  it("칸마다 사진의 같은 자리 색을 읽는다", () => {
    const lab = readCells(photo(512, [220, 120, 120], [120, 200, 120]), landmarks, sampler);
    const at = (row: number, col: number) => lab[(row * GRID + col) * 3 + 1];
    const row = 70;
    const leftCol = [...Array(40).keys()].map((c) => c + 10).find((c) => MEASURED[row * GRID + c])!;
    const rightCol = [...Array(40).keys()]
      .map((c) => 117 - c)
      .find((c) => MEASURED[row * GRID + c])!;
    expect(at(row, leftCol)).toBeGreaterThan(20);
    expect(at(row, rightCol)).toBeLessThan(-20);
  });

  it("얼굴이 사진 밖으로 나간 칸은 색을 내지 않는다", () => {
    const shifted = landmarks.map((p) => ({ x: p.x + 0.6, y: p.y }));
    const lab = readCells(photo(256, [200, 150, 130], [200, 150, 130]), shifted, sampler);
    const right = 70 * GRID + 110;
    expect(Number.isNaN(lab[right * 3])).toBe(true);
  });
});

describe("색 거리", () => {
  it("CIEDE2000 시험 쌍(Sharma 2005)과 같다", () => {
    const pairs: [number[], number[], number][] = [
      [[50, 2.6772, -79.7751], [50, 0, -82.7485], 2.0425],
      [[50, -1.3802, -84.2814], [50, 0, -82.7485], 1.0],
      [[50, 2.5, 0], [56, -27, -3], 31.903],
      [[60.2574, -34.0099, 36.2677], [60.4626, -34.1751, 39.4387], 1.2644],
      [[22.7233, 20.0904, -46.694], [23.0331, 14.973, -42.5619], 2.0373],
    ];
    for (const [a, b, expected] of pairs)
      expect(deltaE2000(a[0], a[1], a[2], b[0], b[1], b[2])).toBeCloseTo(expected, 3);
  });

  it("흰색은 L 100, 회색은 a·b가 0이다", () => {
    const [l, a, b] = rgbToLab(255, 255, 255);
    expect(l).toBeCloseTo(100, 2);
    expect(Math.abs(a)).toBeLessThan(0.01);
    expect(Math.abs(b)).toBeLessThan(0.01);
  });
});
