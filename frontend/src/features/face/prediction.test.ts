import { describe, expect, it } from "vitest";

import { DEFAULT_PREDICTION, FacePredictor } from "./prediction";
import type { FaceFrame } from "./types";
import data from "../../../public/fixtures/faces/front.json";

const sample = (timestamp: number, dx = 0): FaceFrame => ({
  ...(structuredClone(data) as FaceFrame),
  timestamp,
  detectedAt: timestamp,
  landmarks: data.landmarks.map((p) => ({ ...p, x: p.x + dx })),
});

describe("가이드 위치 예측", () => {
  it("영상 좌표에서 관측한 회전 방향과 크기를 사용한다", () => {
    const predictor = new FacePredictor();
    const before = sample(0);
    const origin = before.landmarks[1];
    const angle = 0.02,
      scale = 1.02;
    const current = sample(100);
    current.iod *= scale;
    current.landmarks = current.landmarks.map((p) => {
      const x = (p.x - origin.x) * current.imageSize.width,
        y = (p.y - origin.y) * current.imageSize.height;
      return {
        ...p,
        x:
          origin.x +
          ((x * Math.cos(angle) - y * Math.sin(angle)) * scale) / current.imageSize.width,
        y:
          origin.y +
          ((x * Math.sin(angle) + y * Math.cos(angle)) * scale) / current.imageSize.height,
      };
    });
    predictor.sample(before);
    predictor.sample(current);
    const predicted = predictor.predict(150)!;
    expect(predicted.iod).toBeGreaterThan(current.iod);
    const angleOf = (frame: FaceFrame) =>
      Math.atan2(
        (frame.landmarks[473].y - frame.landmarks[468].y) * frame.imageSize.height,
        (frame.landmarks[473].x - frame.landmarks[468].x) * frame.imageSize.width,
      );
    expect(angleOf(predicted)).toBeGreaterThan(angleOf(current));
  });
  it("이동 방향으로 앞서 그리되 원본 관측을 바꾸지 않는다", () => {
    const predictor = new FacePredictor();
    predictor.sample(sample(0));
    const observed = sample(100, 0.01);
    predictor.sample(observed);
    const predicted = predictor.predict(150)!;
    expect(predicted.landmarks[1].x).toBeGreaterThan(observed.landmarks[1].x);
    expect(observed.landmarks[1].x).toBeCloseTo(data.landmarks[1].x + 0.01);
    expect(predicted.timestamp).toBe(observed.timestamp);
    expect(predictor.predict(150, { ...DEFAULT_PREDICTION, strength: 0 })).toBe(observed);
  });

  it("정지·방향 전환을 다음 관측에 반영한다", () => {
    const predictor = new FacePredictor();
    predictor.sample(sample(0));
    predictor.sample(sample(100, 0.02));
    const stopped = sample(200, 0.02);
    predictor.sample(stopped);
    expect(predictor.predict(230)!.landmarks[1].x).toBeCloseTo(stopped.landmarks[1].x);
    const reversed = sample(300, 0.01);
    predictor.sample(reversed);
    expect(predictor.predict(330)!.landmarks[1].x).toBeLessThan(reversed.landmarks[1].x);
  });

  it("큰 좌표 변화·카메라 크기 변경·재시작에서는 이전 속도를 버린다", () => {
    const predictor = new FacePredictor();
    predictor.sample(sample(0));
    const jump = sample(100, 0.8);
    predictor.sample(jump);
    expect(predictor.predict(130)!.landmarks[1].x).toBe(jump.landmarks[1].x);
    const resized = { ...sample(200, 0.81), imageSize: { width: 640, height: 480 } };
    predictor.sample(resized);
    expect(predictor.predict(230)!.landmarks[1].x).toBe(resized.landmarks[1].x);
    predictor.reset();
    predictor.sample(sample(300));
    expect(predictor.predict(330)!.landmarks[1].x).toBe(data.landmarks[1].x);
  });

  it("hold에서 예측을 멈추고 마지막 실제 검출이 오래되면 숨긴다", () => {
    const predictor = new FacePredictor();
    predictor.sample(sample(0));
    predictor.sample(sample(100, 0.02));
    const held = { ...sample(200, 0.02), detectedAt: 100, trackingState: "hold" as const };
    predictor.sample(held);
    expect(predictor.predict(250)).toBe(held);
    expect(predictor.predict(401)).toBeNull();
    predictor.sample({ ...sample(500), trackingState: "lost" });
    expect(predictor.predict(500)).toBeNull();
  });

  it("예측 이동량을 IOD 비율로 제한한다", () => {
    const predictor = new FacePredictor();
    predictor.sample(sample(0));
    const observed = sample(20, 0.02);
    predictor.sample(observed);
    const predicted = predictor.predict(100, { ...DEFAULT_PREDICTION, strength: 1 })!;
    expect(
      Math.abs(predicted.landmarks[1].x - observed.landmarks[1].x) * observed.imageSize.width,
    ).toBeLessThanOrEqual(observed.iod * DEFAULT_PREDICTION.maxDistance + 1e-6);
  });
});
