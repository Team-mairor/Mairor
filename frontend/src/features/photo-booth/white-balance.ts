/** 파랑 채널에 곱하는 값. 노란 기운은 파랑이 빨강보다 모자란 것이라 파랑만 맞추고, 혈색이 빠지지 않게 나머지는 그대로 둔다. */
export type WhiteBalanceGains = { b: number };

export const NEUTRAL_GAINS: WhiteBalanceGains = { b: 1 };

/** 보정 뒤 피부가 맞추려는 빨강 대비 파랑 비율. 노란 조명이든 아니든 여기로 모은다. */
const TARGET_B_OVER_R = 0.66;

const B_RANGE = [0.85, 1.5] as const;
/** 피부색으로 볼 픽셀이 표본의 이 비율보다 적으면 피부가 없는 장면으로 보고 건너뛴다. */
const MIN_SKIN_RATIO = 0.04;

const clamp = (value: number, [min, max]: readonly [number, number]) =>
  Math.min(max, Math.max(min, value));

function isSkinLike(r: number, g: number, b: number) {
  if (r < 70 || r > 250 || !(r > g && g > b)) return false;
  const gr = g / r;
  const br = b / r;
  return gr >= 0.55 && gr <= 0.95 && br >= 0.35 && br <= 0.9;
}

/**
 * RGBA 표본에서 피부색 픽셀의 평균을 구해, 파랑을 목표 비율로 옮기는 배율을 돌려 준다.
 * 피부색 픽셀이 너무 적으면 null이라 이전 값을 그대로 쓴다.
 */
export function estimateSkinGains(rgba: Uint8ClampedArray): WhiteBalanceGains | null {
  const total = rgba.length / 4;
  let count = 0;
  let sumR = 0;
  let sumB = 0;
  for (let i = 0; i < rgba.length; i += 4) {
    const r = rgba[i];
    const g = rgba[i + 1];
    const b = rgba[i + 2];
    if (!isSkinLike(r, g, b)) continue;
    count += 1;
    sumR += r;
    sumB += b;
  }
  if (total === 0 || count / total < MIN_SKIN_RATIO) return null;

  return { b: clamp(TARGET_B_OVER_R / (sumB / sumR), B_RANGE) };
}

/** 한 번에 확 바뀌어 화면이 깜빡이지 않도록 이전 값에서 조금씩만 옮긴다. */
export function smoothGains(
  previous: WhiteBalanceGains,
  next: WhiteBalanceGains,
  rate = 0.25,
): WhiteBalanceGains {
  return { b: previous.b + (next.b - previous.b) * rate };
}

/** feColorMatrix에 넣는 matrix 값. 파랑에만 배율을 곱한다. */
export function gainsToMatrix({ b }: WhiteBalanceGains) {
  return `1 0 0 0 0  0 1 0 0 0  0 0 ${b.toFixed(4)} 0 0  0 0 0 1 0`;
}
