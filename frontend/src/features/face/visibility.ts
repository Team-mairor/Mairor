import type { FaceFrame, RegionName } from "./types";

/** 부위의 이 비율 이상이 화면 안에 있어야 온전히 보이는 것으로 본다. */
export const MIN_IN_FRAME_RATIO = 0.9;

// 정확하지 않은 가이드는 보여주지 않는다. 추적이 안정적이고 해당 부위가 온전히 보일 때만 그린다.
// 추적기의 minInFrameRatio를 바꿨다면 같은 값을 넘긴다.
export function isGuideVisible(
  frame: FaceFrame | null,
  region?: RegionName,
  minInFrameRatio = MIN_IN_FRAME_RATIO,
): boolean {
  if (!frame || frame.trackingState !== "tracking") return false;
  if (!region) return true;
  const v = frame.regionVisibility[region];
  return v.inFrameRatio >= minInFrameRatio && v.facing;
}
