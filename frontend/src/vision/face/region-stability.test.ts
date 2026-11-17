import { describe, expect, it } from "vitest";

import { RegionStability } from "./region-stability";
import type { FaceFrame } from "./types";
import data from "../../../public/fixtures/faces/front.json";

const frame = (timestamp: number) => ({ ...(structuredClone(data) as FaceFrame), timestamp });

describe("부분 추적의 부위 안정성", () => {
  it("연속 관측을 요구하고 놓친 뒤에는 다시 확인한다", () => {
    const stability = new RegionStability();
    expect(stability.update(frame(0), true)).toEqual([]);
    expect(stability.update(frame(100), true)).toContain("rightEye");
    stability.reset();
    expect(stability.update(frame(200), true)).toEqual([]);
    expect(stability.update(frame(300), false)).toEqual([]);
    expect(stability.update(frame(400), true)).toEqual([]);
  });

  it("급격한 크기 변화와 좌표 누락을 허용하지 않는다", () => {
    const stability = new RegionStability();
    stability.update(frame(0), true);
    const changed = frame(100);
    changed.regions.rightEye.width *= 3;
    changed.landmarks[changed.regions.leftEye.indices[0]].x = NaN;
    const usable = stability.update(changed, true);
    expect(usable).not.toContain("rightEye");
    expect(usable).not.toContain("leftEye");
  });
});
