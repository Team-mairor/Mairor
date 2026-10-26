import { LEFT_IRIS_CENTER, REGIONS, RIGHT_IRIS_CENTER } from "./regions";
import type { EyeState, Point, Pose, RegionInfo, RegionName, RegionVisibility } from "./types";

type Size = { width: number; height: number };

// 정규화 좌표는 가로·세로 단위가 달라 거리·각도는 픽셀 좌표에서 계산한다.
function toPx(p: Point, size: Size) {
  return { x: p.x * size.width, y: p.y * size.height };
}

export function interocularDistance(landmarks: Point[], size: Size): number {
  const r = toPx(landmarks[RIGHT_IRIS_CENTER], size);
  const l = toPx(landmarks[LEFT_IRIS_CENTER], size);
  return Math.hypot(l.x - r.x, l.y - r.y);
}

export function computeRegion(
  name: RegionName,
  landmarks: Point[],
  size: Size,
  iod: number,
): RegionInfo {
  const { indices, axis } = REGIONS[name];
  const points = indices.map((i) => landmarks[i]);

  const center = {
    x: points.reduce((s, p) => s + p.x, 0) / points.length,
    y: points.reduce((s, p) => s + p.y, 0) / points.length,
  };

  const a = toPx(landmarks[axis[0]], size);
  const b = toPx(landmarks[axis[1]], size);
  const angle = Math.atan2(b.y - a.y, b.x - a.x);

  // 부위 축 방향과 수직 방향으로 투영한 범위
  const ux = Math.cos(angle);
  const uy = Math.sin(angle);
  let minU = Infinity;
  let maxU = -Infinity;
  let minV = Infinity;
  let maxV = -Infinity;
  for (const p of points) {
    const { x, y } = toPx(p, size);
    const u = x * ux + y * uy;
    const v = -x * uy + y * ux;
    minU = Math.min(minU, u);
    maxU = Math.max(maxU, u);
    minV = Math.min(minV, v);
    maxV = Math.max(maxV, v);
  }

  return {
    indices,
    center,
    width: (maxU - minU) / iod,
    height: (maxV - minV) / iod,
    angle,
  };
}

/** MediaPipe 얼굴 변환 행렬(4x4, 열 우선)에서 회전 각도를 구한다. */
export function poseFromMatrix(data: number[]): Pose {
  const m = (row: number, col: number) => data[col * 4 + row];
  return {
    yaw: Math.atan2(m(0, 2), m(2, 2)),
    pitch: Math.asin(Math.max(-1, Math.min(1, m(1, 2)))),
    roll: -Math.atan2(m(1, 0), m(1, 1)),
  };
}

export function regionVisibility(
  name: RegionName,
  landmarks: Point[],
  pose: Pose,
  maxYaw: number,
): RegionVisibility {
  const { indices, side } = REGIONS[name];
  const inFrame = indices.filter((i) => {
    const p = landmarks[i];
    return p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1;
  }).length;

  // 본인 기준 왼쪽으로 돌리면(yaw +) 왼쪽 부위가 카메라에서 멀어진다.
  const facing =
    side === "left"
      ? pose.yaw < maxYaw
      : side === "right"
        ? pose.yaw > -maxYaw
        : Math.abs(pose.yaw) < maxYaw;

  return { inFrameRatio: inFrame / indices.length, facing };
}

// eyeBlink 점수는 눈을 완전히 감아도 1까지 오르지 않아 closedBlink를 0으로 보고 늘린다.
export function eyeStateFromBlendshape(
  blink: number,
  closedBlink: number,
  blinkThreshold: number,
): EyeState {
  const openness = Math.max(0, Math.min(1, 1 - blink / closedBlink));
  return { openness, blinking: blink > blinkThreshold };
}
