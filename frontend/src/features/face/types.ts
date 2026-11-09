/** 정규화 좌표 0~1. 원본 카메라 프레임 기준, 좌우는 본인 기준 */
export type Point = { x: number; y: number; z?: number };

export type RegionName =
  | "leftEye"
  | "rightEye"
  | "leftBrow"
  | "rightBrow"
  | "lipsOuter"
  | "lipsInner"
  | "leftCheek"
  | "rightCheek"
  | "faceOval";

/** 얼굴을 처음 찾기 전에는 상태 대신 프레임이 null이다. */
export type TrackingState = "tracking" | "degraded" | "hold" | "lost";

/** 라디안. 본인 기준 왼쪽으로 돌리면 yaw +, 위를 보면 pitch +, 왼쪽으로 기울이면 roll + */
export interface Pose {
  yaw: number;
  pitch: number;
  roll: number;
}

export interface RegionInfo {
  indices: readonly number[];
  center: Point;
  /** IOD(두 홍채 중심 거리) = 1 기준 */
  width: number;
  height: number;
  /** 라디안, 픽셀 좌표 기준 */
  angle: number;
}

export interface RegionVisibility {
  inFrameRatio: number;
  facing: boolean;
}

export interface EyeState {
  /** 0(감음) ~ 1(뜸) */
  openness: number;
  blinking: boolean;
}

export interface FaceFrame {
  version: "0.2";
  meshVersion: "v1";
  timestamp: number;
  imageSize: { width: number; height: number };
  trackingState: TrackingState;
  landmarks: Point[];
  /** 픽셀 */
  iod: number;
  pose: Pose;
  eyes: { left: EyeState; right: EyeState };
  regions: Record<RegionName, RegionInfo>;
  regionVisibility: Record<RegionName, RegionVisibility>;
  /** 마지막 실제 검출 시각. hold에서도 바꾸지 않는다. */
  detectedAt?: number;
  /** 전체 얼굴이 잘려도 연속 관측에서 형태가 안정적인 부위 */
  usableRegions?: RegionName[];
}

/** 원본 프레임 정규화 좌표(0~1)의 사각형 */
export interface NormalizedRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface ViewTransform {
  scale: number;
  offsetX: number;
  offsetY: number;
  mirrored: boolean;
}

export interface MeshAnchor {
  triangle: number;
  /** 합 = 1. 삼각형 밖이면 음수 허용 */
  bary: [number, number, number];
}

export type GuideShape =
  | { type: "point"; at: MeshAnchor }
  /** brush면 따라 그릴 선이 아니라 결 방향의 붓 자국(눈썹 결·속눈썹)으로 그린다 */
  | { type: "polyline"; path: MeshAnchor[]; width: number; brush?: boolean }
  | { type: "polygon"; outline: MeshAnchor[] }
  | { type: "arrow"; from: MeshAnchor; to: MeshAnchor };
