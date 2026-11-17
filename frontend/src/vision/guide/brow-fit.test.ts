import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { REGIONS, type FaceFrame, type MeshAnchor } from "@/vision/face";
import type { FaceMesh } from "@/vision/overlay";

import {
  alignBrowStep,
  axisOf,
  browSpans,
  findBrows,
  fitBrowStep,
  fromLocal,
  toLocal,
  type Pixels,
} from "./brow-fit";
import { anchorTools, buildDefaultGuideSet } from "./default-guides";
import type { GuideItem, GuideStep } from "./types";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const frame: FaceFrame = read("../../../public/fixtures/faces/front.json");
const mesh: FaceMesh = {
  ...read("../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../shared/face-mesh/uv.v1.json"),
};
const { uvPt, anchorAt } = anchorTools(mesh);

type Pt = { x: number; y: number };
const LOWER = { rightBrow: [55, 65, 52, 53, 46], leftBrow: [285, 295, 282, 283, 276] };
const UPPER = { rightBrow: [107, 66, 105, 63, 70], leftBrow: [336, 296, 334, 293, 300] };
type Side = keyof typeof LOWER;

function inside(poly: Pt[], p: Pt) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x)
      hit = !hit;
  }
  return hit;
}

const uvOf = ({ triangle, bary }: MeshAnchor): Pt => {
  const [a, b, c] = mesh.triangles[triangle].map(uvPt);
  return {
    x: a.x * bary[0] + b.x * bary[1] + c.x * bary[2],
    y: a.y * bary[0] + b.y * bary[1] + c.y * bary[2],
  };
};

/** 아랫선에서 윗선 쪽으로 from~to만큼인 띠 (점 번호 i, j 사이를 t로 나눈 자리) */
function band(
  points: (i: number, j: number, t: number) => Pt,
  side: Side,
  from: number,
  to: number,
) {
  const lower = LOWER[side].map((i, k) => points(i, UPPER[side][k], from));
  const upper = UPPER[side].map((j, k) => points(LOWER[side][k], j, to));
  return [...lower, ...upper.reverse()];
}

const uvLerp = (i: number, j: number, t: number) => ({
  x: uvPt(i).x + (uvPt(j).x - uvPt(i).x) * t,
  y: uvPt(i).y + (uvPt(j).y - uvPt(i).y) * t,
});

/** 맨피부 밝기 skin 위에 고른 띠마다 dark로 칠한 사진 */
function photo(bands: Pt[][], skin = 200, dark = 70): Pixels {
  return layered(
    bands.map((poly) => ({ poly, v: dark })),
    skin,
  );
}

/** 뒤에 오는 층이 앞 층을 덮는 사진 */
function layered(layers: { poly: Pt[]; v: number }[], skin = 200): Pixels {
  const { width, height } = frame.imageSize;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      let v = skin;
      for (const layer of layers) if (inside(layer.poly, { x, y })) v = layer.v;
      data.set([v, v, v, 255], (y * width + x) * 4);
    }
  return { width, height, data };
}

const pxLerp = (i: number, j: number, t: number) => {
  const { width, height } = frame.imageSize;
  const a = frame.landmarks[i];
  const b = frame.landmarks[j];
  return { x: (a.x + (b.x - a.x) * t) * width, y: (a.y + (b.y - a.y) * t) * height };
};

describe("등록 사진의 원래 눈썹 찾기", () => {
  it("맨피부보다 어두운 눈썹을 양쪽 모두 찾는다", () => {
    const brows = findBrows(
      photo([band(pxLerp, "rightBrow", 0, 1), band(pxLerp, "leftBrow", 0, 1)]),
      frame,
      mesh,
    );
    for (const side of ["rightBrow", "leftBrow"] as const) {
      const outline = brows[side]!.map(uvOf);
      // 눈썹 가운데는 안, 눈썹 위 이마는 밖
      expect(inside(outline, uvLerp(LOWER[side][2], UPPER[side][2], 0.5))).toBe(true);
      expect(inside(outline, uvLerp(LOWER[side][2], UPPER[side][2], 2))).toBe(false);
    }
  });

  it("어두운 곳이 없으면 찾지 않는다", () => {
    expect(findBrows(photo([]), frame, mesh)).toEqual({});
  });

  it("옅고 가는 눈썹은 아래 그림자와 위 앞머리 가닥을 빼고 찾는다", () => {
    const side = "rightBrow";
    // 앞머리(0)에서 꼬리(4)까지 k, 아랫선(0)에서 윗선(1)까지 t인 자리
    const at = (k: number, t: number) => {
      const i = Math.min(3, Math.floor(k));
      const f = k - i;
      const a = pxLerp(LOWER[side][i], UPPER[side][i], t);
      const b = pxLerp(LOWER[side][i + 1], UPPER[side][i + 1], t);
      return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
    };
    const strand = [at(0.8, 1), at(0.95, 1), at(0.95, 3), at(0.8, 3)];
    const brows = findBrows(
      layered([
        { poly: band(pxLerp, side, -1.2, 0), v: 186 },
        { poly: band(pxLerp, side, -0.6, 0), v: 174 },
        { poly: band(pxLerp, side, 0, 1), v: 140 },
        { poly: strand, v: 60 },
      ]),
      frame,
      mesh,
    );
    const outline = brows[side]!.map(uvOf);
    const uvAt = (k: number, t: number) => {
      const i = Math.min(3, Math.floor(k));
      const f = k - i;
      const a = uvLerp(LOWER[side][i], UPPER[side][i], t);
      const b = uvLerp(LOWER[side][i + 1], UPPER[side][i + 1], t);
      return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
    };
    expect(inside(outline, uvAt(2, 0.5))).toBe(true);
    expect(inside(outline, uvAt(0.9, 0.5))).toBe(true);
    expect(inside(outline, uvAt(2, -0.3))).toBe(false);
    expect(inside(outline, uvAt(0.9, 1.5))).toBe(false);
  });

  it("앞머리 아래 눈 안쪽 그림자로 테두리가 꺾여 내려가지 않는다", () => {
    const side = "rightBrow";
    // k는 앞머리(0)~꼬리(4), t는 랜드마크 아랫선(0)~윗선(1). 실제 눈썹은 랜드마크보다 가늘고 위에 있다
    const at = (lerpOf: typeof pxLerp, k: number, t: number) => {
      const i = Math.max(0, Math.min(3, Math.floor(k)));
      const f = k - i;
      const a = lerpOf(LOWER[side][i], UPPER[side][i], t);
      const b = lerpOf(LOWER[side][i + 1], UPPER[side][i + 1], t);
      return { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
    };
    const shadow = [
      at(pxLerp, -0.4, 0.4),
      at(pxLerp, 0.6, 0.4),
      at(pxLerp, 0.6, -2),
      at(pxLerp, -0.4, -2),
    ];
    const brows = findBrows(
      layered([
        { poly: shadow, v: 150 },
        { poly: band(pxLerp, side, 0.4, 1), v: 120 },
      ]),
      frame,
      mesh,
    );
    const outline = brows[side]!.map(uvOf);
    expect(inside(outline, at(uvLerp, 2, 0.7))).toBe(true);
    expect(inside(outline, at(uvLerp, 0.2, 0.7))).toBe(true);
    expect(inside(outline, at(uvLerp, 0.2, -0.3))).toBe(false);
  });

  it("한쪽만 있으면 그쪽만 찾는다", () => {
    const brows = findBrows(photo([band(pxLerp, "rightBrow", 0, 1)]), frame, mesh);
    expect(brows.rightBrow).toBeDefined();
    expect(brows.leftBrow).toBeUndefined();
  });
});

describe("원래 눈썹에 맞춘 눈썹 가이드", () => {
  const axisFor = (side: Side) =>
    axisOf(uvPt(LOWER[side][0]), uvPt(LOWER[side][LOWER[side].length - 1]));
  /** 랜드마크 눈썹 좌표로 head~tail, 높이 -0.05~0.15인 원래 눈썹 */
  const own = (side: Side, head: number, tail: number) => {
    const axis = axisFor(side);
    const steps = Array.from({ length: 9 }, (_, k) => head + ((tail - head) * k) / 8);
    return [
      ...steps.map((sv) => anchorAt(fromLocal(axis, sv, -0.05))),
      ...[...steps].reverse().map((sv) => anchorAt(fromLocal(axis, sv, 0.15))),
    ];
  };
  const step = (
    guides: GuideItem[],
    regions: GuideStep["regions"] = ["rightBrow", "leftBrow"],
  ) => ({
    stepId: "s8",
    order: 1,
    title: "",
    regions,
    guides,
    source: "template" as const,
  });
  const hair = (side: Side, sv: number): GuideItem => {
    const axis = axisFor(side);
    return {
      type: "polyline",
      brush: true,
      width: 0.013,
      path: [anchorAt(fromLocal(axis, sv, 0)), anchorAt(fromLocal(axis, sv, 0.1))],
    };
  };
  const along = (side: Side, a: MeshAnchor) => toLocal(axisFor(side), uvOf(a));

  it("가이드 앞머리를 원래 눈썹 앞머리로 옮기고 높이는 그대로 둔다", () => {
    const fitted = alignBrowStep(
      step([hair("rightBrow", 0), hair("rightBrow", 0.5), hair("rightBrow", 1)]),
      { rightBrow: own("rightBrow", 0.1, 0.9) },
      mesh,
    );
    const roots = fitted.guides.map((g) =>
      along("rightBrow", (g as Extract<GuideItem, { type: "polyline" }>).path[0]),
    );
    // 꼬리는 랜드마크 꼬리보다 짧게 찾혀도 랜드마크 꼬리(1)까지 본다
    expect(roots[0].s).toBeCloseTo(0.1, 1);
    expect(roots[1].s).toBeCloseTo(0.55, 1);
    expect(roots[2].s).toBeCloseTo(1, 1);
    for (const root of roots) expect(root.h).toBeCloseTo(0, 1);
    expect(fitted.guides).toHaveLength(3);
  });

  it("영역도 같은 비율로 옮기고, 원래 눈썹을 못 찾은 쪽은 그대로 둔다", () => {
    const axis = axisFor("rightBrow");
    const area: GuideItem = {
      type: "polygon",
      outline: [
        [0, 0],
        [1, 0],
        [1, 0.2],
        [0, 0.2],
      ].map(([sv, h]) => anchorAt(fromLocal(axis, sv, h))),
      region: "rightBrow",
    };
    const left = hair("leftBrow", 0.5);
    const fitted = alignBrowStep(
      step([area, left]),
      { rightBrow: own("rightBrow", -0.1, 1.1) },
      mesh,
    );
    const moved = fitted.guides[0] as Extract<GuideItem, { type: "polygon" }>;
    expect(along("rightBrow", moved.outline[0]).s).toBeCloseTo(-0.1, 1);
    expect(along("rightBrow", moved.outline[1]).s).toBeCloseTo(1.1, 1);
    expect(fitted.guides[1]).toBe(left);
  });

  it("찾은 길이가 이상하거나 원래 눈썹이 없거나 눈썹 단계가 아니면 바꾸지 않는다", () => {
    const brow = step([hair("rightBrow", 0.5)]);
    expect(alignBrowStep(brow, { rightBrow: own("rightBrow", 0, 0.4) }, mesh)).toBe(brow);
    expect(alignBrowStep(brow, null, mesh)).toBe(brow);
    expect(alignBrowStep(brow, {}, mesh)).toBe(brow);
    const lip = step([hair("rightBrow", 0.5)], ["lipsOuter"]);
    expect(alignBrowStep(lip, { rightBrow: own("rightBrow", 0.1, 0.9) }, mesh)).toBe(lip);
  });

  it("기본 가이드 결은 원래 눈썹 윗선·아랫선을 따라 다시 그린다", () => {
    const axis = axisFor("rightBrow");
    // 가운데가 솟은 원래 눈썹
    const columns = Array.from({ length: 9 }, (_, k) => k / 8);
    const arch = (sv: number) => 0.15 + 0.12 * Math.sin(Math.PI * sv);
    const arched = [
      ...columns.map((sv) => anchorAt(fromLocal(axis, sv, -0.05))),
      ...[...columns].reverse().map((sv) => anchorAt(fromLocal(axis, sv, arch(sv)))),
    ];
    const base = buildDefaultGuideSet(mesh, REGIONS).steps.find((st) => st.stepId === "brow")!;
    const fitted = fitBrowStep(base, { rightBrow: arched }, mesh);
    const hairs = fitted.guides as Extract<GuideItem, { type: "polyline" }>[];
    const right = hairs.filter((h) => h.region === "rightBrow");
    expect(right).toHaveLength(40);
    const outline = arched.map(uvOf);
    expect(right.every((h) => inside(outline, uvOf(h.path[1])))).toBe(true);
    // 가운데 결 끝은 랜드마크 윗선보다 높은 산까지 올라간다
    const middle = right.filter((h) => Math.abs(along("rightBrow", h.path[0]).s - 0.5) < 0.08);
    expect(Math.max(...middle.map((h) => along("rightBrow", h.path[2]).h))).toBeGreaterThan(0.2);
    // 원래 눈썹을 못 찾은 왼쪽은 기본 결 그대로
    const left = base.guides.filter((g) => !fitted.guides.includes(g));
    expect(left).toHaveLength(40);
    expect(fitted.guides).toHaveLength(80);
  });

  it("영상에서 찾은 영역은 모양을 바꾸지 않고 앞머리·꼬리만 맞춘다", () => {
    const axis = axisFor("rightBrow");
    const area: GuideItem = {
      type: "polygon",
      outline: [
        [0, 0],
        [1, 0],
        [1, 0.2],
        [0, 0.2],
      ].map(([sv, h]) => anchorAt(fromLocal(axis, sv, h))),
      region: "rightBrow",
    };
    const fitted = fitBrowStep(step([area]), { rightBrow: own("rightBrow", 0.1, 1.05) }, mesh);
    const moved = fitted.guides[0] as Extract<GuideItem, { type: "polygon" }>;
    expect(along("rightBrow", moved.outline[0]).s).toBeCloseTo(0.1, 1);
    expect(along("rightBrow", moved.outline[1]).s).toBeCloseTo(1.05, 1);
    expect(along("rightBrow", moved.outline[2]).h).toBeCloseTo(0.2, 1);
  });

  it("결을 다시 그려도 도형을 그리는 순서는 그대로 둔다", () => {
    const axis = axisFor("rightBrow");
    const area: GuideItem = {
      type: "polygon",
      outline: [
        [0, 0],
        [1, 0],
        [1, 0.2],
      ].map(([sv, h]) => anchorAt(fromLocal(axis, sv, h))),
      region: "rightBrow",
    };
    const left = hair("leftBrow", 0.5);
    const fitted = fitBrowStep(
      step([area, hair("rightBrow", 0.2), left, hair("rightBrow", 0.8)]),
      { rightBrow: own("rightBrow", 0.1, 1.05) },
      mesh,
    );
    expect(fitted.guides[0].type).toBe("polygon");
    expect(fitted.guides.slice(1, 41).every((g) => g.region === "rightBrow")).toBe(true);
    expect(fitted.guides[41]).toBe(left);
    expect(fitted.guides).toHaveLength(42);
  });

  it("들쭉날쭉한 원래 눈썹 윗선은 매끄러운 곡선으로 다듬는다", () => {
    const axis = axisFor("rightBrow");
    const columns = Array.from({ length: 25 }, (_, k) => k / 24);
    // 윗선이 칸마다 0.06씩 오르내리는 눈썹
    const jagged = [
      ...columns.map((sv) => anchorAt(fromLocal(axis, sv, -0.05))),
      ...[...columns].reverse().map((sv, k) => anchorAt(fromLocal(axis, sv, k % 2 ? 0.21 : 0.09))),
    ];
    const span = browSpans({ rightBrow: jagged }, mesh).rightBrow!;
    for (const p of span.high) expect(Math.abs(p.h - 0.15)).toBeLessThan(0.025);
    for (const p of span.low) expect(Math.abs(p.h + 0.05)).toBeLessThan(0.015);
  });
});
