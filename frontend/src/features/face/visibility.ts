import type { FaceFrame, RegionName } from "./types";

/** 부위의 이 비율 이상이 화면 안에 있어야 온전히 보이는 것으로 본다. */
export const MIN_IN_FRAME_RATIO = 0.9;
/** 이미 화면 밖으로 본 부위는 이만큼 더 들어와야 다시 보이는 것으로 본다 (경계에서 깜빡이지 않게) */
export const RECOVER_IN_FRAME_MARGIN = 0.03;

/** 부위가 카메라 쪽을 향하고 충분히 화면 안에 있는지 */
export function isRegionInView(
  frame: FaceFrame,
  region: RegionName,
  minInFrameRatio = MIN_IN_FRAME_RATIO,
): boolean {
  const v = frame.regionVisibility[region];
  return v.inFrameRatio >= minInFrameRatio && v.facing;
}

// 정확하지 않은 가이드는 보여주지 않는다. 추적이 안정적이고 해당 부위가 온전히 보일 때만 그린다.
// 추적기의 minInFrameRatio를 바꿨다면 같은 값을 넘긴다.
export function isGuideVisible(
  frame: FaceFrame | null,
  region?: RegionName,
  minInFrameRatio = MIN_IN_FRAME_RATIO,
): boolean {
  if (!frame || frame.trackingState !== "tracking") return false;
  if (!region) return true;
  return isRegionInView(frame, region, minInFrameRatio);
}

/**
 * 잠깐 놓친 동안(hold)에는 새로 판정하지 않고 직전 판정을 그대로 쓴다.
 * hold 프레임은 직전 결과를 복사한 것이라, 숨겨 두었던 것을 부정확한 위치에 다시 보이게 하지 않는다.
 * 깜빡임 때 보이던 가이드·화장이 깜빡이지 않게 한다.
 */
export class HoldVisibility {
  private visible = false;

  /** 판정 대상이 바뀌었을 때(예: 튜토리얼 단계) 직전 판정을 버린다. */
  reset() {
    this.visible = false;
  }

  update(frame: FaceFrame | null, isVisible: () => boolean): boolean {
    if (frame?.trackingState !== "hold") this.visible = isVisible();
    return this.visible;
  }
}
