import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { REGIONS } from "@/features/face";
import { buildDefaultGuideSet, type GuideSet } from "@/features/guide";

const read = (path: string) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const mesh = {
  ...read("../../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../../shared/face-mesh/uv.v1.json"),
};
const baseline: GuideSet = read("../../../../public/fixtures/guides/compare-baseline.json");
describe("268 가이드 비교", () => {
  it("적용된 기본값은 픽스처와 같고 변경 전 기준은 그대로 남는다", () => {
    const current = buildDefaultGuideSet(mesh, REGIONS);
    const fixture = read("../../../../public/fixtures/guides/compare-candidate.json");
    const steps = current.steps.filter((s) => ["blush", "brow"].includes(s.stepId));
    const widths = (set: GuideSet["steps"]) =>
      set.flatMap((s) => s.guides.flatMap((g) => (g.type === "polyline" ? [g.width] : [])));
    // 삼각함수 계산의 환경별 미세 오차만 허용하고 구조·좌표는 정확히 비교한다.
    const withoutWidths = (set: GuideSet["steps"]) =>
      set.map((s) => ({
        ...s,
        guides: s.guides.map((g) => (g.type === "polyline" ? { ...g, width: 0 } : g)),
      }));
    expect(withoutWidths(steps)).toEqual(withoutWidths(fixture.steps));
    const actual = widths(steps);
    const expected = widths(fixture.steps);
    expect(actual).toHaveLength(expected.length);
    actual.forEach((width, i) => expect(width).toBeCloseTo(expected[i], 12));
    expect(
      baseline.steps.find((s) => s.stepId === "brow")!.guides.filter((g) => g.type === "polyline"),
    ).toHaveLength(32);
  });
  it("블러셔 시작점·방향을 유지하고 타원·가는 눈썹 결을 만든다", () => {
    const candidate = buildDefaultGuideSet(mesh, REGIONS);
    const blush = candidate.steps.find((s) => s.stepId === "blush")!;
    expect(blush.guides.filter((g) => g.type !== "polygon")).toEqual(
      baseline.steps[0].guides.filter((g) => g.type !== "polygon"),
    );
    const hairs = candidate.steps
      .find((s) => s.stepId === "brow")!
      .guides.filter((g) => g.type === "polyline");
    expect(blush.guides.filter((g) => g.type === "polygon")).not.toEqual(
      baseline.steps[0].guides.filter((g) => g.type === "polygon"),
    );
    expect(
      blush.guides.filter((g) => g.type === "polygon").every((g) => g.outline.length === 32),
    ).toBe(true);
    expect(
      candidate.steps.find((s) => s.stepId === "brow")!.guides.every((g) => g.type === "polyline"),
    ).toBe(true);
    expect(hairs).toHaveLength(80);
    expect(hairs.every((g) => g.brush && g.width > 0 && g.width <= 0.013)).toBe(true);
    expect(candidate).not.toEqual(baseline);
  });
  it("한쪽 눈썹 높이가 달라도 반대쪽과 독립적으로 랜드마크를 따라간다", () => {
    const guides = buildDefaultGuideSet(mesh, REGIONS).steps.find(
      (s) => s.stepId === "brow",
    )!.guides;
    const y = (a: { triangle: number; bary: number[] }, shifted: boolean) =>
      mesh.triangles[a.triangle].reduce(
        (sum: number, v: number, k: number) =>
          sum + (mesh.uv[v][1] + (shifted && mesh.uv[v][0] < 0.5 ? -0.04 : 0)) * a.bary[k],
        0,
      );
    for (const [i, g] of guides.entries()) {
      if (g.type !== "polyline") throw new Error("결만 있어야 합니다");
      for (const a of g.path) {
        expect(y(a, true) - y(a, false)).toBeCloseTo(i < 40 ? -0.04 : 0, 4);
      }
    }
  });
});
