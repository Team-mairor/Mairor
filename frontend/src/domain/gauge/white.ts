import { REGIONS, type Point } from "@/vision/face";
import type { FaceMesh } from "@/vision/overlay";

import { polygonPoints } from "./area";
import type { Pixels } from "./cells";
import measure from "../../../../shared/gauge/measure.v1.json" with { type: "json" };

/** 두 눈 구멍 안 지도 점마다 속한 메시 삼각형의 세 꼭짓점과 비율 */
export interface EyeSampler {
  corners: Int32Array;
  weights: Float32Array;
  eyes: Uint8Array;
  size: number;
}

const EYES = [
  { name: "leftEye", center: 473, ring: [474, 475, 476, 477] },
  { name: "rightEye", center: 468, ring: [469, 470, 471, 472] },
] as const;

const INSET_SHARE = 0.05;
const IRIS_SCALE = 1.2;

/** 두 눈 구멍(눈 테두리 안) 지도 점을 한 번만 고른다. 점마다 그 점을 덮는 삼각형을 찾는다 */
export function eyeSampler(mesh: FaceMesh): EyeSampler {
  const holes = EYES.map(({ name }) =>
    REGIONS[name].indices.map((i) => mesh.uv[i] as [number, number]),
  );
  const eyePoints = holes.map((hole) => polygonPoints([hole]));
  const points = eyePoints.flat();
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [minX, maxX, minY, maxY] = [
    Math.min(...xs),
    Math.max(...xs),
    Math.min(...ys),
    Math.max(...ys),
  ];
  // 눈 구멍 둘레에 걸친 삼각형만 본다
  const near = mesh.triangles.filter((tri) => {
    const us = tri.map((i) => mesh.uv[i][0]);
    const vs = tri.map((i) => mesh.uv[i][1]);
    return (
      Math.max(...us) >= minX &&
      Math.min(...us) <= maxX &&
      Math.max(...vs) >= minY &&
      Math.min(...vs) <= maxY
    );
  });
  const corners: number[] = [];
  const weights: number[] = [];
  const eyes: number[] = [];
  for (const [eye, samples] of eyePoints.entries()) {
    for (const [px, py] of samples) {
      for (const tri of near) {
        const [[ax, ay], [bx, by], [cx, cy]] = tri.map((i) => mesh.uv[i]);
        const area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
        if (Math.abs(area) < 1e-12) continue;
        const wb = ((px - ax) * (cy - ay) - (cx - ax) * (py - ay)) / area;
        const wc = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area;
        const wa = 1 - wb - wc;
        if (wa < -1e-9 || wb < -1e-9 || wc < -1e-9) continue;
        corners.push(...tri);
        weights.push(wa, wb, wc);
        eyes.push(eye);
        break;
      }
    }
  }
  return {
    corners: Int32Array.from(corners),
    weights: Float32Array.from(weights),
    eyes: Uint8Array.from(eyes),
    size: weights.length / 3,
  };
}

type PixelPoint = readonly [number, number];

const distance = ([ax, ay]: PixelPoint, [bx, by]: PixelPoint) => Math.hypot(ax - bx, ay - by);

function segmentDistance(p: PixelPoint, a: PixelPoint, b: PixelPoint) {
  const [dx, dy] = [b[0] - a[0], b[1] - a[1]];
  const length2 = dx * dx + dy * dy;
  if (!length2) return distance(p, a);
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length2));
  return distance(p, [a[0] + dx * t, a[1] + dy * t]);
}

function irisRadius(points: PixelPoint[]) {
  let diameter = 0;
  for (let a = 0; a < points.length; a++)
    for (let b = a + 1; b < points.length; b++)
      diameter = Math.max(diameter, distance(points[a], points[b]));
  return (diameter / 2) * IRIS_SCALE;
}

/** 프레임에서 눈 구멍 점마다 sRGB(0~255)를 둘레 네 픽셀로 섞어 읽는다. 사진 밖 점은 NaN이다 */
export function readEyePixels(pixels: Pixels, landmarks: Point[], s: EyeSampler): Float32Array {
  const { width, height, data } = pixels;
  const out = new Float32Array(s.size * 3).fill(NaN);
  const at = (i: number): PixelPoint | null => {
    const p = landmarks[i];
    return p ? [p.x * width, p.y * height] : null;
  };
  const eyes = EYES.map(({ name, center, ring }) => {
    const outline = REGIONS[name].indices.map(at).filter((p): p is PixelPoint => p !== null);
    const axis = REGIONS[name].axis.map(at);
    const irisCenter = at(center);
    const irisRing = ring.map(at).filter((p): p is PixelPoint => p !== null);
    return {
      outline,
      inset:
        axis[0] && axis[1] ? distance(axis[0], axis[1]) * INSET_SHARE : Number.POSITIVE_INFINITY,
      irisCenter,
      irisRadius: irisRing.length === ring.length ? irisRadius(irisRing) : 0,
    };
  });
  for (let k = 0; k < s.size; k++) {
    const [a, b, c] = [0, 1, 2].map((n) => landmarks[s.corners[k * 3 + n]]);
    if (!a || !b || !c) continue;
    const [wa, wb, wc] = [0, 1, 2].map((n) => s.weights[k * 3 + n]);
    const x = (a.x * wa + b.x * wb + c.x * wc) * width;
    const y = (a.y * wa + b.y * wb + c.y * wc) * height;
    if (x < 0 || y < 0 || x > width - 1 || y > height - 1) continue;
    const eye = eyes[s.eyes[k]];
    const point: PixelPoint = [x, y];
    if (
      eye.outline.length < 3 ||
      eye.outline.some(
        (edge, i) =>
          segmentDistance(point, edge, eye.outline[(i + 1) % eye.outline.length]) < eye.inset,
      ) ||
      (eye.irisCenter && eye.irisRadius > 0 && distance(point, eye.irisCenter) <= eye.irisRadius)
    )
      continue;
    const x0 = Math.floor(x);
    const y0 = Math.floor(y);
    const x1 = Math.min(x0 + 1, width - 1);
    const y1 = Math.min(y0 + 1, height - 1);
    const right = x - x0;
    const down = y - y0;
    for (let ch = 0; ch < 3; ch++) {
      const at = (xx: number, yy: number) => data[(yy * width + xx) * 4 + ch];
      const top = at(x0, y0) * (1 - right) + at(x1, y0) * right;
      const bottom = at(x0, y1) * (1 - right) + at(x1, y1) * right;
      out[k * 3 + ch] = Math.round(top * (1 - down) + bottom * down);
    }
  }
  return out;
}

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(mid)] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** numpy percentile(선형 보간)과 같은 값 */
function percentile(values: number[], q: number) {
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/**
 * 맨얼굴 사진들의 흰자 색(sRGB 0~255 세 개). 사진마다 밝기 위 white.share이고 채널 하나라도
 * white.clip 이상이 아닌 점의 가운데 값을 흰자로 내고, 그 사진별 흰자의 채널별 가운데 값이다(AI eye_white와 같은 규칙).
 * 흰자 점이 measure.white.minPixels보다 적으면 null이다
 */
export function whiteOfFrames(frames: Float32Array[]): [number, number, number] | null {
  if (!frames.length) return null;
  const whites = frames.flatMap((frame) => {
    const pixels: [number, number, number][] = [];
    for (let k = 0; k < frame.length / 3; k++) {
      const rgb = [frame[k * 3], frame[k * 3 + 1], frame[k * 3 + 2]] as [number, number, number];
      if (rgb.every((v) => !Number.isNaN(v))) pixels.push(rgb);
    }
    if (!pixels.length) return [];
    const light = pixels.map(([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b);
    const floor = percentile(light, 1 - measure.white.share);
    const kept = pixels.filter((p, i) => light[i] >= floor && Math.max(...p) < measure.white.clip);
    if (kept.length < measure.white.minPixels) return [];
    return [[0, 1, 2].map((ch) => median(kept.map((p) => p[ch]))) as [number, number, number]];
  });
  if (!whites.length) return null;
  return [0, 1, 2].map((ch) => median(whites.map((white) => white[ch]))) as [
    number,
    number,
    number,
  ];
}
