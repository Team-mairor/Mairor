import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { REGIONS, type GuideShape } from "@/features/face";

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
