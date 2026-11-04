export function hex(c: string) {
  return [1, 3, 5].map((k) => parseInt(c.slice(k, k + 2), 16));
}

/** 색 거리 기반 유사도 (정렬용·화면 미노출) */
export function similarity(a: string, b: string) {
  const x = hex(a);
  const y = hex(b);
  return 100 - Math.sqrt(x.reduce((t, v, i) => t + (v - y[i]) ** 2, 0)) / 4.4;
}

/** 색 계열 분류 (바꾸기 패널 톤 필터) */
export function toneOf(c: string) {
  const [r, g, b] = hex(c);
  return r - b > 70 && g < r * 0.62
    ? "코랄·레드"
    : r - g < 45
      ? "로즈"
      : (r + g + b) / 3 > 190
        ? "누드"
        : "브라운";
}
