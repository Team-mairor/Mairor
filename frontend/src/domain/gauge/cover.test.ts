import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import type { FaceMesh } from "@/vision/overlay";

import { cellSampler } from "./cells";
import { areaCover, blankCovered, readCover, type OcclusionMask } from "./cover";
import { GRID, MEASURED } from "./spec";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const mesh: FaceMesh = {
  ...read("../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../shared/face-mesh/uv.v1.json"),
};
const sampler = cellSampler(mesh);
/** 얼굴 지도를 그대로 찍은 사진처럼, 점 위치를 UV와 같게 둔다 */
const landmarks = mesh.uv.map(([x, y]) => ({ x, y }));
const PHOTO = { width: 512, height: 512 };

/** 사진 전체(512)를 덮는 정사각형 위에서, 칠한 곳(visit이 true)을 가림으로 둔 가림 표 */
function mask(size: number, occluded: (x: number, y: number) => boolean): OcclusionMask {
  const data = new Uint8Array(size * size);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) data[y * size + x] = occluded(x / size, y / size) ? 1 : 0;
  return { size, data, box: { left: 0, top: 0, side: PHOTO.width } };
}

const measuredCells = Uint8Array.from(MEASURED);

describe("칸 가린 몫", { timeout: 20_000 }, () => {
  it("가림이 없으면 모든 칸이 0이다", () => {
    const cover = readCover(
      mask(384, () => false),
      PHOTO,
      landmarks,
      sampler,
    );
    expect(Math.max(...cover)).toBe(0);
    expect(areaCover(cover, measuredCells)).toBe(0);
  });

  it("얼굴을 모두 덮으면 재는 칸의 가린 몫이 1이다", () => {
    const cover = readCover(
      mask(384, () => true),
      PHOTO,
      landmarks,
      sampler,
    );
    expect(areaCover(cover, measuredCells)).toBeGreaterThan(0.97);
  });

  it("가로 왼쪽 절반만 가리면 왼쪽 칸만 가리고 영역 가린 몫이 반쯤이다", () => {
    const cover = readCover(
      mask(384, (u) => u < 0.5),
      PHOTO,
      landmarks,
      sampler,
    );
    const row = 70;
    const left = [...Array(40).keys()].map((c) => c + 10).find((c) => MEASURED[row * GRID + c])!;
    const right = [...Array(40).keys()]
      .map((c) => GRID - 11 - c)
      .find((c) => MEASURED[row * GRID + c])!;
    expect(cover[row * GRID + left]).toBeGreaterThan(0.9);
    expect(cover[row * GRID + right]).toBe(0);
    const share = areaCover(cover, measuredCells);
    expect(share).toBeGreaterThan(0.4);
    expect(share).toBeLessThan(0.6);
  });

  it("얼굴 일부만 덮으면 영역 몫이 그 비율에 맞고 0.2 문턱을 가른다", () => {
    // 가로 선 하나 아래(v > 0.7)만 가림: 입 · 턱 쪽
    const cover = readCover(
      mask(384, (_u, v) => v > 0.7),
      PHOTO,
      landmarks,
      sampler,
    );
    const share = areaCover(cover, measuredCells);
    expect(share).toBeGreaterThan(0.05);
    expect(share).toBeLessThan(0.5);
    // 영역을 가린 곳과 겹치지 않는 윗부분으로 좁히면 몫이 0이다
    const upper = Uint8Array.from(measuredCells);
    for (let k = 0; k < upper.length; k++) if (Math.floor(k / GRID) > 70) upper[k] = 0;
    expect(areaCover(cover, upper)).toBe(0);
  });

  it("정사각형 밖은 가림이 없고, 입력 크기가 달라도 같은 자리를 가린다", () => {
    // 정사각형이 사진 오른쪽 절반(left 256, side 256)만 덮고 그 안은 모두 가림
    const half: OcclusionMask = {
      size: 128,
      data: new Uint8Array(128 * 128).fill(1),
      box: { left: 256, top: 0, side: 256 },
    };
    const cover = readCover(half, PHOTO, landmarks, sampler);
    const row = 70;
    const col = [...Array(40).keys()].map((c) => c + 10).find((c) => MEASURED[row * GRID + c])!;
    expect(cover[row * GRID + col]).toBe(0);
    const fine = readCover(
      mask(384, (u) => u >= 0.5),
      PHOTO,
      landmarks,
      sampler,
    );
    const coarse = readCover(
      mask(192, (u) => u >= 0.5),
      PHOTO,
      landmarks,
      sampler,
    );
    expect(
      Math.abs(areaCover(fine, measuredCells) - areaCover(coarse, measuredCells)),
    ).toBeLessThan(0.02);
  });

  it("영역 칸이 없으면 영역 가린 몫은 0이다", () => {
    expect(areaCover(new Float32Array(GRID * GRID).fill(1), new Uint8Array(GRID * GRID))).toBe(0);
  });
});

describe("가린 칸 비우기", () => {
  it("가린 몫이 0보다 큰 칸의 세 값을 비우고 나머지와 원래 표는 그대로 둔다", () => {
    const grid = new Float32Array(GRID * GRID * 3).fill(50);
    const cover = new Float32Array(GRID * GRID);
    cover[5] = 0.01;
    cover[9] = 1;
    const out = blankCovered(grid, cover);
    for (const k of [5, 9])
      for (let ch = 0; ch < 3; ch++) expect(Number.isNaN(out[k * 3 + ch])).toBe(true);
    expect(out[0]).toBe(50);
    expect(out[6 * 3]).toBe(50);
    expect(grid[5 * 3]).toBe(50);
  });
});
