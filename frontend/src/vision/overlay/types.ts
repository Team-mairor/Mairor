import type { MeshAnchor, RegionName } from "@/vision/face";

export type MakeupKind = "foundation" | "eyeshadow" | "eyeliner" | "blush" | "lip";

export type LayerShape = "polygon" | "uvMask" | "polyline";

export type BlendMode = "normal" | "multiply";

/** 화장 레이어 하나. 크기 단위(feather·width)는 IOD = 1 기준 */
export interface MakeupLayer {
  stepId: string;
  makeup: MakeupKind;
  regions: RegionName[];
  /** polygon에서 빼는 영역 */
  exclude?: RegionName[];
  shape: LayerShape;
  /** 가장자리 흐림 전체 폭. 경계선이 0.5이고 안쪽·바깥쪽으로 절반씩 흐려진다 */
  feather?: number;
  /** shape가 uvMask일 때 마스크 PNG 경로 (레이어 파일 기준 상대 경로) */
  uvMask?: string;
  /** shape가 polyline일 때 그리는 순서대로 */
  path?: MeshAnchor[];
  width?: number;
  lineCap?: "round" | "butt";
  /** #RRGGBB. null이면 그리지 않는다 */
  color: string | null;
  colorSource: "frame" | "product" | "estimated" | "manual" | null;
  opacity: number;
  blend: BlendMode;
  source: "extracted" | "template" | "manual";
}

/** 배열 순서 = 겹치는 순서 */
export interface LayerSet {
  videoId: string;
  meshVersion: "v1";
  layers: MakeupLayer[];
}
