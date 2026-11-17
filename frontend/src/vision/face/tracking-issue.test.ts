// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";

import { trackingIssue } from "./tracking-issue";
import type { FaceFrame } from "./types";
import data from "../../../public/fixtures/faces/front.json";

const frame = (faceOvalInFrame: number): FaceFrame => {
  const f = structuredClone(data) as FaceFrame;
  f.regionVisibility.faceOval.inFrameRatio = faceOvalInFrame;
  return f;
};

describe("trackingIssue", () => {
  afterEach(() => document.documentElement.classList.remove("mirror"));

  it("미러필름 위에서는 턱까지 얼굴 전체가 카메라에 들어와야 그린다", () => {
    document.documentElement.classList.add("mirror");
    expect(trackingIssue(frame(0.8))).toBe("out-of-frame");
    expect(trackingIssue(frame(1))).toBe(null);
  });

  it("미러필름에서 한 번 숨긴 뒤에는 여유만큼 더 들어와야 다시 그린다", () => {
    document.documentElement.classList.add("mirror");
    expect(trackingIssue(frame(0.91), "out-of-frame")).toBe("out-of-frame");
    expect(trackingIssue(frame(0.91), null)).toBe(null);
    expect(trackingIssue(frame(0.95), "out-of-frame")).toBe(null);
  });

  it("일반 모드에서는 윤곽이 조금 잘려도 핵심 부위가 보이면 그린다", () => {
    expect(trackingIssue(frame(0.8))).toBe(null);
  });
});
