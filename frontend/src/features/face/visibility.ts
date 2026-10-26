import type { FaceFrame, RegionName } from "./types";

const MIN_REGION_IN_FRAME = 0.9;

// 정확하지 않은 가이드는 보여주지 않는다. 추적이 안정적이고 해당 부위가 온전히 보일 때만 그린다.
export function isGuideVisible(frame: FaceFrame | null, region?: RegionName): boolean {
  if (!frame || frame.trackingState !== "tracking") return false;
  if (!region) return true;
  const v = frame.regionVisibility[region];
  return v.inFrameRatio >= MIN_REGION_IN_FRAME && v.facing;
}
