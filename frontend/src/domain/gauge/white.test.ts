import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { REGIONS } from "@/vision/face";
import type { FaceMesh } from "@/vision/overlay";

import { areaCells, madeCells } from "./area";
import { GRID, MEASURED } from "./spec";
import { eyeSampler, readEyePixels, whiteOfFrames } from "./white";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const mesh: FaceMesh = {
  ...read("../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../shared/face-mesh/uv.v1.json"),
};

/** UV 네모를 얼굴 메시 기준점으로 바꾼 영역 묶음 */
function squareSet(u0: number, v0: number, u1: number, v1: number) {
  const anchor = (u: number, v: number) => {
    for (const [t, tri] of mesh.triangles.entries()) {
      const [[ax, ay], [bx, by], [cx, cy]] = tri.map((i) => mesh.uv[i]);
      const area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
      const wb = ((u - ax) * (cy - ay) - (cx - ax) * (v - ay)) / area;
      const wc = ((bx - ax) * (v - ay) - (u - ax) * (by - ay)) / area;
      if (wb >= 0 && wc >= 0 && wb + wc <= 1)
        return { triangle: t, bary: [1 - wb - wc, wb, wc] as [number, number, number] };
    }
    throw new Error("얼굴 밖");
  };
  return {
    region: "rightCheek" as const,
    source: "extracted" as const,
    guides: [
      {
        type: "polygon" as const,
        outline: [anchor(u0, v0), anchor(u1, v0), anchor(u1, v1), anchor(u0, v1)],
      },
    ],
  };
}

// 128 × 128칸을 여러 번 계산해 전체 시험을 함께 돌릴 때 느려질 수 있다
describe("영역 칸", { timeout: 20_000 }, () => {
  it("테두리 안이 칸의 절반 이상이고 재는 칸인 칸만 고른다", () => {
    const cells = areaCells(squareSet(0.25, 0.55, 0.35, 0.65), mesh);
    const at = (u: number, v: number) => cells[Math.floor(v * GRID) * GRID + Math.floor(u * GRID)];
    expect(at(0.3, 0.6)).toBe(1);
    expect(at(0.2, 0.6)).toBe(0);
    expect(cells.every((c, k) => !c || MEASURED[k])).toBe(true);
    // 0.1 × 0.1 UV는 약 12.8 × 12.8칸이다
    const count = cells.reduce((a, b) => a + b, 0);
    expect(count).toBeGreaterThan(130);
    expect(count).toBeLessThan(190);
  });

  it("단계의 모든 묶음 칸을 합친다", () => {
    const a = areaCells(squareSet(0.25, 0.55, 0.3, 0.6), mesh);
    const b = areaCells(squareSet(0.7, 0.55, 0.75, 0.6), mesh);
    const made = madeCells([a, b]);
    expect(made.reduce((x, y) => x + y, 0)).toBe(
      a.reduce((x, y) => x + y, 0) + b.reduce((x, y) => x + y, 0),
    );
  });
});

// 128 × 128칸을 여러 번 계산해 전체 시험을 함께 돌릴 때 느려질 수 있다
describe("흰자 색", { timeout: 20_000 }, () => {
  const sampler = eyeSampler(mesh);
  const landmarks = mesh.uv.map(([x, y]) => ({ x, y }));

  it("두 눈 구멍 안 점을 골라 사진에서 읽는다", () => {
    expect(sampler.size).toBeGreaterThan(200);
    const data = new Uint8ClampedArray(512 * 512 * 4).fill(200);
    const rgb = readEyePixels({ width: 512, height: 512, data }, landmarks, sampler);
    const kept = [...rgb].filter((v) => !Number.isNaN(v));
    expect(kept.length).toBeGreaterThan(60);
    expect(kept.length).toBeLessThan(rgb.length);
    expect(kept.every((v) => v === 200)).toBe(true);
  });

  it("눈동자와 눈 테두리 5% 안쪽은 흰자에서 뺀다", () => {
    const withIris = [...landmarks];
    for (const [name, center, ring] of [
      ["rightEye", 468, [469, 470, 471, 472]],
      ["leftEye", 473, [474, 475, 476, 477]],
    ] as const) {
      const [a, b] = REGIONS[name].axis.map((i) => landmarks[i]);
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
      withIris[center] = mid;
      const radius = Math.hypot(a.x - b.x, a.y - b.y) * 0.12;
      for (const [i, angle] of ring.map((i, k) => [i, (Math.PI * k) / 2] as const))
        withIris[i] = {
          x: mid.x + Math.cos(angle) * radius,
          y: mid.y + Math.sin(angle) * radius,
        };
    }
    const data = new Uint8ClampedArray(512 * 512 * 4).fill(200);
    const without = readEyePixels({ width: 512, height: 512, data }, landmarks, sampler);
    const filtered = readEyePixels({ width: 512, height: 512, data }, withIris, sampler);
    const count = (values: Float32Array) => [...values].filter((v) => !Number.isNaN(v)).length;

    expect(count(filtered)).toBeLessThan(count(without));
  });

  it("밝은 위 25% 중 반사광을 뺀 점의 가운데 값이다", () => {
    // 점 200개: 어두운 눈동자 120, 흰자 60(밝기 180~239), 반사광 20
    const frame = new Float32Array(600);
    for (let k = 0; k < 200; k++) {
      const v = k < 120 ? 40 : k < 180 ? 180 + (k - 120) : 255;
      frame.set([v, v - 10, v - 20], k * 3);
    }
    const white = whiteOfFrames([frame, frame, frame]);
    // 위 25%는 흰자 30개(210~239)와 반사광 20개이고, 반사광을 빼면 흰자 30개의 가운데 값이다
    expect(white).toEqual([224.5, 214.5, 204.5]);
  });

  it("흰자 점이 너무 적거나 사진이 없으면 못 잰다", () => {
    expect(whiteOfFrames([])).toBeNull();
    expect(whiteOfFrames([new Float32Array([200, 200, 200, 210, 210, 210])])).toBeNull();
  });
});
