// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { distanceHint } from "./face-register";
import type { FaceFrame } from "./types";
import data from "../../../public/fixtures/faces/front.json";

/** 원본 영상에서 얼굴을 가로로 dx(영상 폭 대비)만큼 옮긴 프레임 */
const shifted = (dx: number): FaceFrame => {
  const f = structuredClone(data) as FaceFrame;
  f.landmarks = f.landmarks.map((p) => ({ ...p, x: p.x + dx }));
  return f;
};

const circle = (size: number) => {
  const el = document.createElement("div");
  Object.defineProperty(el, "clientWidth", { value: size });
  return el;
};

describe("distanceHint", () => {
  it("가운데 얼굴은 원 안으로 본다", () => {
    expect(distanceHint(shifted(0), circle(400))).toBe(null);
  });

  it("일반 모드도 원 안에 그리는 자리로 판정한다", () => {
    // 1280×720 영상에서 폭의 0.1 옮기면 영상 기준으로는 허용치(0.15) 안이지만, 원(가운데 720 정사각형) 기준으로는 0.18이라 벗어난다
    expect(distanceHint(shifted(0.1))).toBe(null);
    expect(distanceHint(shifted(0.1), circle(400))).not.toBe(null);
  });
});
