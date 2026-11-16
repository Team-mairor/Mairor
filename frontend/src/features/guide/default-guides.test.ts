import { readFileSync } from "node:fs";

import { describe, expect, it, vi } from "vitest";

import { REGIONS, type GuideShape, type MeshAnchor } from "@/features/face";

import { resolveSubStep } from "./area";
import { anchorTools, buildDefaultGuideSet } from "./default-guides";

const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const mesh = {
  ...read("../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../shared/face-mesh/uv.v1.json"),
};

describe("아이라인 바른 자리별 기본 가이드", () => {
  const steps = buildDefaultGuideSet(mesh, REGIONS).steps;
  const { at, uvPt } = anchorTools(mesh);

  /** 오른쪽(사용자 기준, 영상 왼쪽)부터 [시작점, 선] 쌍으로 꺼낸다 */
  const pairs = (stepId: string) => {
    const guides = steps.find((s) => s.stepId === stepId)?.guides ?? [];
    return [0, 2].map((i) => [guides[i], guides[i + 1]] as [GuideShape, GuideShape]);
  };

  // 오른쪽 눈은 바깥쪽이 영상 왼쪽(x 감소), 왼쪽 눈은 영상 오른쪽(x 증가)
  const cases = [
    { stepId: "eyelinerWaterline", length: 9, starts: [133, 362], ends: [33, 263] },
    { stepId: "eyelinerUnder", length: 5, starts: [145, 374], ends: [33, 263] },
  ];

  for (const { stepId, length, starts, ends } of cases) {
    it(`${stepId}는 눈마다 의도한 점에서 시작해 눈꼬리 쪽으로 가고, 시작점 표시가 선 첫 점과 같다`, () => {
      pairs(stepId).forEach(([start, line], eye) => {
        expect(line.type).toBe("polyline");
        if (line.type !== "polyline" || start.type !== "point") throw new Error("모양이 다릅니다");
        expect(line.path).toHaveLength(length);
        expect(line.width).toBe(0.03);
        expect(line.path[0]).toEqual(at(starts[eye]));
        expect(line.path.at(-1)).toEqual(at(ends[eye]));
        expect(start.at).toEqual(line.path[0]);
        const outward = uvPt(ends[eye]).x - uvPt(starts[eye]).x;
        expect(eye === 0 ? outward < 0 : outward > 0).toBe(true);
      });
      const [[, right], [, left]] = pairs(stepId);
      expect(right).not.toEqual(left);
    });
  }
});

describe("코 블러셔 기본 가이드", () => {
  const set = buildDefaultGuideSet(mesh, REGIONS);
  const nose = set.steps.find((s) => s.stepId === "blushNose");
  const { uvPt } = anchorTools(mesh);

  /** 메시 기준점을 UV 좌표로 */
  const uvOf = ({ triangle, bary }: MeshAnchor) => {
    const corners = (mesh.triangles[triangle] as number[]).map(uvPt);
    return {
      x: corners.reduce((sum, p, k) => sum + p.x * bary[k], 0),
      y: corners.reduce((sum, p, k) => sum + p.y * bary[k], 0),
    };
  };
  const inside = (polygon: { x: number; y: number }[], p: { x: number; y: number }) => {
    let hit = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const [a, b] = [polygon[i], polygon[j]];
      if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x)
        hit = !hit;
    }
    return hit;
  };

  it("얼굴 가운데 도형 하나만 그리고 화살표는 없다", () => {
    expect(nose?.regions).toEqual(["rightEye", "leftEye"]);
    expect(nose?.guides).toHaveLength(1);
    expect(nose?.guides[0].type).toBe("polygon");
  });

  it("코끝부터 눈 앞머리 사이 콧대 위까지 덮는다", () => {
    const shape = nose?.guides[0];
    if (shape?.type !== "polygon") throw new Error("모양이 다릅니다");
    const outline = shape.outline.map(uvOf);
    // 코끝(1·4), 콧등(5·195), 콧대(197·6), 눈 앞머리 사이(168 바로 아래)
    for (const i of [1, 4, 5, 195, 197, 6]) expect(inside(outline, uvPt(i))).toBe(true);
    // 볼(205·425)과 콧볼 바깥(129·358)은 들어가지 않는다
    for (const i of [205, 425, 129, 358]) expect(inside(outline, uvPt(i))).toBe(false);
  });

  it("하이라이트 콧대 도형과 볼 블러셔와 다른 도형이다", () => {
    const highlight = set.steps.find((s) => s.stepId === "highlight")?.guides[0];
    const blush = set.steps.find((s) => s.stepId === "blush");
    expect(nose?.guides[0]).not.toBe(highlight);
    expect(nose?.guides[0]).not.toEqual(highlight);
    expect(blush?.guides).not.toEqual(nose?.guides);
  });

  it("AI가 보낸 blushNose 키를 경고 없이 코 블러셔 기본 가이드로 그린다", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const step = resolveSubStep(
      {
        subStepId: "s22b-1",
        order: 1,
        status: "template",
        reasons: ["notAnalyzed"],
        templateId: "blushNose",
        guideSets: [],
      },
      set,
      "blush",
    );
    expect(step?.guides).toEqual(nose?.guides);
    expect(step?.title).toBe(nose?.title);
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
