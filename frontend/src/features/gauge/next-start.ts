// 묶음 둘째 단계부터는 준비 카드 없이, 앞 단계에서 「다음」을 누르기 직전 사진으로 단계 시작 기준을 잡는다.
import { buildBaseline, type Baseline } from "./baseline";
import type { CellLab } from "./cells";
import { FRAMES } from "./spec";
import { frameReason, NEXT_START, nextStartPicks, type FrameState } from "./stability";

/** 앞 단계 동안 0.2초마다 남긴 사진 한 장 */
export interface TailShot {
  at: number;
  state: FrameState;
  grid: CellLab;
}

/** 다음 단계 시작 기준을 고를 수 있는 기간(nextStart.windowMs)보다 오래된 사진을 버린다 */
export const trimTail = (tail: readonly TailShot[], now: number) =>
  tail.filter((shot) => now - shot.at <= NEXT_START.windowMs);

/**
 * 앞 단계 사진을 다음 단계 화장 종류로 다시 걸러 다음 단계 시작 기준을 만든다. 모자라면 null이다.
 * 조명 바뀜은 견줄 다음 단계 기준이 아직 없어 보지 않는다
 */
export function nextStartBaseline(
  tail: readonly TailShot[],
  makeup: string,
  pressedMs: number,
  center: number | null,
): Baseline | null {
  if (center === null) return null;
  const picks = nextStartPicks(
    tail.map((shot) => shot.at),
    tail.map((shot) => {
      if (Math.abs((shot.state.pitch ?? center) - center) > FRAMES.frontMax) return "turned";
      // frameReason의 카메라 정면 pitch 대신 위에서 확인한 개인 정면 조건을 쓴다
      return frameReason({ ...shot.state, pitch: 0, drift: null }, makeup);
    }),
    pressedMs,
  );
  return picks ? buildBaseline(picks.map((i) => tail[i].grid)) : null;
}
