import { REGIONS, REGION_NAMES } from "./regions";
import type { FaceFrame, RegionName } from "./types";

/** 한 부위만 보일 때는 두 번 연속 크기와 좌표가 유효해야 부분 추적에 쓴다. */
export class RegionStability {
  private previous: FaceFrame | null = null;

  reset() {
    this.previous = null;
  }

  update(frame: FaceFrame, reliable: boolean): RegionName[] {
    const previous = this.previous;
    this.previous = reliable ? frame : null;
    if (!reliable || !previous || frame.timestamp - previous.timestamp > 400) return [];
    return REGION_NAMES.filter((name) => {
      const region = frame.regions[name];
      const before = previous.regions[name];
      const width = region.width * frame.iod;
      const oldWidth = before.width * previous.iod;
      const points = REGIONS[name].indices.map((i) => frame.landmarks[i]);
      return (
        points.every((p) => p && Number.isFinite(p.x) && Number.isFinite(p.y)) &&
        Number.isFinite(width) &&
        width >= 3 &&
        oldWidth > 0 &&
        width / oldWidth >= 0.65 &&
        width / oldWidth <= 1.55 &&
        Math.hypot(
          (region.center.x - before.center.x) * frame.imageSize.width,
          (region.center.y - before.center.y) * frame.imageSize.height,
        ) <= frame.iod
      );
    });
  }
}
