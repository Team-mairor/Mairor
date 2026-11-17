export interface Summary {
  n: number;
  min: number;
  median: number;
  p90: number;
  max: number;
  mean: number;
}

const round = (value: number) => Math.round(value * 10) / 10;

/** ms 값 목록의 최소 · 가운데 · 90% · 최대 · 평균(소수 첫째 자리). 비었으면 null */
export function summarize(values: readonly number[]): Summary | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.ceil(q * sorted.length) - 1)];
  const median =
    sorted.length % 2
      ? sorted[(sorted.length - 1) / 2]
      : (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2;
  return {
    n: sorted.length,
    min: round(sorted[0]),
    median: round(median),
    p90: round(at(0.9)),
    max: round(sorted[sorted.length - 1]),
    mean: round(sorted.reduce((sum, v) => sum + v, 0) / sorted.length),
  };
}

/** 두 가림 표(0 · 1)의 같은 픽셀 비율과, 가림으로 본 곳의 겹침(IoU). 둘 다 가림이 없으면 iou는 null */
export function compareMasks(a: Uint8Array, b: Uint8Array) {
  if (a.length !== b.length) throw new Error("가림 표 크기가 다릅니다");
  let same = 0;
  let both = 0;
  let either = 0;
  for (let i = 0; i < a.length; i++) {
    if (a[i] === b[i]) same++;
    if (a[i] && b[i]) both++;
    if (a[i] || b[i]) either++;
  }
  return { samePixels: same / a.length, iou: either === 0 ? null : both / either };
}
