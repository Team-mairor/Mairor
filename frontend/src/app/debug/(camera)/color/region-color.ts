import { rgbToLab, type Lab } from "@/lib/color";

export type Px = { x: number; y: number };

/** 이보다 밝은 채널이 있으면 반사광으로 보고 뺀다 */
const HIGHLIGHT = 250;

export function inside(p: Px, poly: readonly Px[]): boolean {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (a.y > p.y !== b.y > p.y && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) {
      hit = !hit;
    }
  }
  return hit;
}

/** 꼭짓점 평균을 중심으로 k배 키운다 */
export function grow(poly: readonly Px[], k: number): Px[] {
  const cx = poly.reduce((s, p) => s + p.x, 0) / poly.length;
  const cy = poly.reduce((s, p) => s + p.y, 0) / poly.length;
  return poly.map((p) => ({ x: cx + (p.x - cx) * k, y: cy + (p.y - cy) * k }));
}

export function deltaE(a: Lab, b: Lab): number {
  return Math.hypot(a.l - b.l, a.a - b.a, a.b - b.b);
}

export type RegionSample = { inner: Lab; band: Lab; innerCount: number; bandCount: number };

/**
 * 영역 안 평균 색과 영역을 band배 키운 둘레 띠의 평균 색.
 * hole(입 안 등)은 양쪽 모두에서 빼고, clip(얼굴 윤곽 등)이 있으면 그 밖도 뺀다. 좌표는 영상 픽셀 기준
 */
export function sampleRegion(
  image: { data: Uint8ClampedArray; width: number; height: number },
  outline: readonly Px[],
  band: number,
  hole: readonly Px[] | null = null,
  clip: readonly Px[] | null = null,
): RegionSample | null {
  const outer = grow(outline, band);
  const xs = outer.map((p) => p.x);
  const ys = outer.map((p) => p.y);
  const x0 = Math.max(0, Math.floor(Math.min(...xs)));
  const x1 = Math.min(image.width - 1, Math.ceil(Math.max(...xs)));
  const y0 = Math.max(0, Math.floor(Math.min(...ys)));
  const y1 = Math.min(image.height - 1, Math.ceil(Math.max(...ys)));
  const sum = { inner: [0, 0, 0, 0], band: [0, 0, 0, 0] };

  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      const p = { x: x + 0.5, y: y + 0.5 };
      if (!inside(p, outer) || (hole && inside(p, hole)) || (clip && !inside(p, clip))) continue;
      const i = (y * image.width + x) * 4;
      const r = image.data[i];
      const g = image.data[i + 1];
      const b = image.data[i + 2];
      if (Math.max(r, g, b) >= HIGHLIGHT) continue;
      const s = inside(p, outline) ? sum.inner : sum.band;
      s[0] += r;
      s[1] += g;
      s[2] += b;
      s[3] += 1;
    }
  }
  const [ir, ig, ib, innerCount] = sum.inner;
  const [br, bg, bb, bandCount] = sum.band;
  if (!innerCount || !bandCount) return null;
  return {
    inner: rgbToLab(ir / innerCount, ig / innerCount, ib / innerCount),
    band: rgbToLab(br / bandCount, bg / bandCount, bb / bandCount),
    innerCount,
    bandCount,
  };
}

export function mean(values: readonly number[]): number {
  return values.reduce((s, v) => s + v, 0) / values.length;
}

export function sd(values: readonly number[]): number {
  const m = mean(values);
  return Math.sqrt(values.reduce((s, v) => s + (v - m) ** 2, 0) / values.length);
}

export function meanLab(values: readonly Lab[]): Lab {
  return {
    l: mean(values.map((v) => v.l)),
    a: mean(values.map((v) => v.a)),
    b: mean(values.map((v) => v.b)),
  };
}
