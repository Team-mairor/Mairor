import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { landmarkMotion, mirroredRegionBox } from "./regions";
import type { FaceFrame } from "./types";

const frame: FaceFrame = JSON.parse(
  readFileSync(new URL("../../../public/fixtures/faces/front.json", import.meta.url), "utf8"),
);

describe("mirroredRegionBox", () => {
  it("부위를 감싸는 픽셀 정사각형을 사진 안에 둔다", () => {
    const box = mirroredRegionBox(frame, ["lipsOuter"])!;
    const { width, height } = frame.imageSize;
    expect(box.w * width).toBeCloseTo(box.h * height);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.w).toBeLessThanOrEqual(1);
    expect(box.y + box.h).toBeLessThanOrEqual(1);
  });

  it("좌우 반전한 사진 기준이라 사용자 오른쪽 눈(원본 x < 0.5)은 사진 오른쪽에 온다", () => {
    const box = mirroredRegionBox(frame, ["rightEye"])!;
    expect(box.x + box.w / 2).toBeGreaterThan(0.5);
  });

  it("얼굴 전체 단계나 부위 없는 단계는 자르지 않는다", () => {
    expect(mirroredRegionBox(frame, ["faceOval", "leftCheek"])).toBeNull();
    expect(mirroredRegionBox(frame, [])).toBeNull();
  });
});

describe("landmarkMotion", () => {
  it("그대로면 0, 모든 점이 눈 사이 거리만큼 옮겨 가면 1", () => {
    expect(landmarkMotion(frame, frame)).toBe(0);
    const dx = frame.iod / frame.imageSize.width;
    const moved = { ...frame, landmarks: frame.landmarks.map((p) => ({ ...p, x: p.x + dx })) };
    expect(landmarkMotion(frame, moved)).toBeCloseTo(1);
  });
});
