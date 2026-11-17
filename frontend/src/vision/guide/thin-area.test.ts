import { describe, expect, it } from "vitest";

import type { GuideShape } from "@/vision/face";
import type { FaceMesh } from "@/vision/overlay";

import { isThinArea } from "./thin-area";

/** 꼭짓점마다 그 점 하나로 된 삼각형을 두어, 얼굴 주소가 곧 그 UV가 되게 한 가짜 얼굴 지도 */
const meshOf = (uv: [number, number][]): FaceMesh => ({
  triangles: uv.map((_, i) => [i, i, i]),
  uv,
});

/** 가로 width, 세로 height인 UV 사각형 영역 */
const rect = (width: number, height: number): { guide: GuideShape; mesh: FaceMesh } => {
  const mesh = meshOf([
    [0.3, 0.3],
    [0.3 + width, 0.3],
    [0.3 + width, 0.3 + height],
    [0.3, 0.3 + height],
  ]);
  return {
    mesh,
    guide: {
      type: "polygon",
      outline: mesh.uv.map((_, triangle) => ({ triangle, bary: [1, 0, 0] })),
    },
  };
};

describe("isThinArea", () => {
  it("아이라인처럼 얇은 띠는 얇은 영역이다", () => {
    const { guide, mesh } = rect(0.12, 0.006);
    expect(isThinArea(guide, mesh)).toBe(true);
  });

  it("애교살 띠처럼 두께가 기준보다 두꺼우면 얇은 영역이 아니다", () => {
    const { guide, mesh } = rect(0.12, 0.03);
    expect(isThinArea(guide, mesh)).toBe(false);
  });

  it("영역이 아닌 도형은 얇은 영역이 아니다", () => {
    const mesh = meshOf([[0.3, 0.3]]);
    const point: GuideShape = { type: "point", at: { triangle: 0, bary: [1, 0, 0] } };
    expect(isThinArea(point, mesh)).toBe(false);
  });
});
