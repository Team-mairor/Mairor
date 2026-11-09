import {
  FRAME_STALE_MS,
  MIN_IN_FRAME_RATIO,
  RECOVER_IN_FRAME_MARGIN,
  REGIONS,
  type FaceFrame,
  type NormalizedRect,
  type RegionName,
} from "@/features/face";

import { isStepInCrop } from "./tutorial-crop";
import type { GuideStep } from "./types";

export const GUIDE_TURN = { fadeStart: 0.45, hidden: 0.75, max: 1.05 } as const;
/** 얼굴 윤곽처럼 양쪽에 걸친 도형의 먼 쪽. 볼 뒤로 넘어간 윤곽이 얼굴 위에 그려지지 않게 일찍 숨긴다 */
export const FAR_SIDE_TURN = { ...GUIDE_TURN, fadeStart: 0.17, hidden: 0.3 } as const;
export const GUIDE_STALE_MS = FRAME_STALE_MS;

const smoothstep = (lo: number, hi: number, value: number) => {
  const t = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

export function turnAlpha(
  yaw: number,
  side: "left" | "right" | "center",
  turn: { fadeStart: number; hidden: number; max: number } = GUIDE_TURN,
) {
  if (!Number.isFinite(yaw) || Math.abs(yaw) >= turn.max) return 0;
  const away = side === "left" ? yaw : side === "right" ? -yaw : Math.abs(yaw);
  return 1 - smoothstep(turn.fadeStart, turn.hidden, away);
}

export function guideRegionAlpha(
  frame: FaceFrame | null,
  region: RegionName,
  recovering = false,
  min = MIN_IN_FRAME_RATIO,
) {
  if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold") return 0;
  if (frame.trackingState !== "tracking" && !frame.usableRegions?.includes(region)) return 0;
  const limit = min + (recovering ? RECOVER_IN_FRAME_MARGIN : 0);
  if (region !== "faceOval" && frame.regionVisibility[region].inFrameRatio < limit) return 0;
  if (region === "faceOval")
    return Number.isFinite(frame.pose.yaw) && Math.abs(frame.pose.yaw) < GUIDE_TURN.max ? 1 : 0;
  return turnAlpha(frame.pose.yaw, REGIONS[region].side);
}

export function isStepVisible(step: GuideStep, frame: FaceFrame | null, min = MIN_IN_FRAME_RATIO) {
  const regions = step.regions.length ? step.regions : (["faceOval"] as const);
  return regions.some((region) => guideRegionAlpha(frame, region, false, min) > 0);
}

/** 관측마다 판정해, 그리는 빈도가 달라져도 복귀 조건은 같게 유지한다. */
export class GuideVisibility {
  private step: GuideStep | null = null;
  /** 마지막으로 판정한 관측. 시각이 같은 정적 픽스처끼리 바꿔도 다시 판정한다 */
  private observed: FaceFrame | null = null;
  private timestamp = -Infinity;
  private alphas = new Map<RegionName, number>();
  private crop: NormalizedRect | null = null;

  reset() {
    this.step = null;
    this.observed = null;
    this.timestamp = -Infinity;
    this.alphas.clear();
  }

  update(
    step: GuideStep | null,
    frame: FaceFrame | null,
    now = frame?.timestamp ?? 0,
    crop: NormalizedRect | null = null,
  ) {
    if (this.crop !== crop) {
      this.observed = null;
      this.timestamp = -Infinity;
      this.crop = crop;
    }
    if (this.step !== step) {
      this.reset();
      this.step = step;
    }
    if (!frame || now - (frame.detectedAt ?? now) > GUIDE_STALE_MS) {
      this.alphas.clear();
      return false;
    }
    if (frame !== this.observed || frame.timestamp !== this.timestamp) {
      this.observed = frame;
      this.timestamp = frame.timestamp;
      if (frame.trackingState !== "hold") {
        for (const region of Object.keys(REGIONS) as RegionName[]) {
          const recovering = this.alphas.has(region) && !this.alphas.get(region);
          this.alphas.set(
            region,
            crop &&
              !isStepInCrop(
                { regions: [region] },
                frame,
                crop,
                recovering ? RECOVER_IN_FRAME_MARGIN : 0,
              )
              ? 0
              : guideRegionAlpha(frame, region, recovering),
          );
        }
      }
    }
    const regions = step?.regions.length ? step.regions : (["faceOval"] as const);
    return !!step && regions.some((name) => this.alpha(name) > 0);
  }

  alpha(region: RegionName) {
    return this.alphas.get(region) ?? 0;
  }
}
