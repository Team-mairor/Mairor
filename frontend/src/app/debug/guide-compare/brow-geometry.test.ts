import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import type { FaceFrame } from "@/features/face";
import type { FaceMesh } from "@/features/overlay";

import { fitDetectedBrows, imageAnchor } from "./brow-geometry";

const read = (p: string) => JSON.parse(readFileSync(new URL(p, import.meta.url), "utf8"));
const frame: FaceFrame = read("../../../../public/fixtures/faces/front.json");
const mesh: FaceMesh = {
  ...read("../../../../../shared/face-mesh/triangles.v1.json"),
  ...read("../../../../../shared/face-mesh/uv.v1.json"),
};
const crop = { x: 0, y: 0, size: 1280 };
function mask() {
  const result = new Uint8Array(512 * 512);
  for (const [inner, outer] of [
    [55, 46],
    [285, 276],
  ]) {
    const a = frame.landmarks[inner],
      b = frame.landmarks[outer];
    const dx = (b.x - a.x) * 1280,
      dy = (b.y - a.y) * 720,
      length = Math.hypot(dx, dy),
      ux = dx / length,
      uy = dy / length;
    const nx = ux >= 0 ? uy : -uy,
      ny = -Math.abs(ux);
    for (let y = 0; y < 512; y++)
      for (let x = 0; x < 512; x++) {
        const px = (x + 0.5) * 2.5 - a.x * 1280,
          py = (y + 0.5) * 2.5 - a.y * 720;
        const s = (px * ux + py * uy) / length,
          h = (px * nx + py * ny) / length;
        // 좌우 다른 두께: 대칭으로 복사하지 않는지 확인한다.
        if (s > 0.03 && s < 0.98 && h > -0.03 && h < (inner === 55 ? 0.22 : 0.32))
          result[y * 512 + x] = 1;
      }
  }
  return result;
}
describe("브라우저 눈썹 검출 도형", () => {
  it("실제 마스크의 좌우 영역을 독립적으로 메시 위 결로 바꾼다", () => {
    const result = fitDetectedBrows(mask(), 512, crop, frame, mesh);
    expect(result.step.guides).toHaveLength(80);
    expect(result.outline).toHaveLength(2);
    for (const guide of result.step.guides) {
      if (guide.type !== "polyline") throw new Error("시작점 없이 결만 있어야 합니다");
      for (const anchor of guide.path) {
        expect(anchor.bary.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
        expect(anchor.triangle).toBeLessThan(mesh.triangles.length);
      }
    }
  });
  it("빈 검출·한쪽만 검출되면 성공한 기본 가이드로 대체하지 않는다", () => {
    expect(() => fitDetectedBrows(new Uint8Array(512 * 512), 512, crop, frame, mesh)).toThrow(
      "양쪽 눈썹",
    );
    const one = mask();
    for (let y = 0; y < 512; y++) one.fill(0, y * 512 + 256, (y + 1) * 512);
    expect(() => fitDetectedBrows(one, 512, crop, frame, mesh)).toThrow();
  });
  it("얼굴 밖 좌표를 무리하게 메시에 붙이지 않는다", () => {
    expect(imageAnchor({ x: -10, y: -10 }, frame, mesh)).toBeNull();
  });
});
