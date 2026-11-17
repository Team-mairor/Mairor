import type { GaugeDisplay } from "./stability";

/** 게이지 막대에서 너무 진하다고 보고 멈추는 값. 막대 50이 레퍼런스라 70은 레퍼런스의 1.4배다 */
export const TOO_DARK_BAR = 70;
/** 한 번 멈춘 뒤 다시 멈추려면 막대가 이 값 아래로 내려와야 한다 */
export const TOO_DARK_RELEASE_BAR = 60;
/** 너무 진한 상태가 이만큼 이어져야 멈춘다. 순간 흔들림에 창이 뜨지 않게 한다 */
export const TOO_DARK_HOLD_MS = 1000;

type Shown = Pick<GaugeDisplay, "bar" | "label" | "stale"> | null | undefined;

/** 단계를 넘기기 전에 더 바르라고 물을 만큼 연하다. 못 재는 동안 남은 마지막 값은 보지 않는다 */
export function needsMore(display: Shown): boolean {
  return !!display && display.label === "lighter" && display.bar !== null && !display.stale;
}

/** 너무 진해 멈추고 확인할 값이다 */
export function isTooDark(display: Shown): boolean {
  return !!display && display.bar !== null && !display.stale && display.bar >= TOO_DARK_BAR;
}

/** 진한 정도가 충분히 내려와 다시 알려도 된다 */
export function isTooDarkReleased(display: Shown): boolean {
  return !!display && display.bar !== null && !display.stale && display.bar < TOO_DARK_RELEASE_BAR;
}
