import type { FaceFrame, MeshAnchor, Point } from "@/features/face";
import type { GuideStep } from "@/features/guide";
import type { FaceMesh } from "@/features/overlay";

export type FaceCrop = { x: number; y: number; size: number };
export type BrowDetection = { step: GuideStep; outline: MeshAnchor[][] };

/** 검출 순간의 영상 좌표를 메시 기준점으로 바꿔 다음 얼굴 프레임에도 붙어 있게 한다. */
export function imageAnchor(p: Point, frame: FaceFrame, mesh: FaceMesh): MeshAnchor | null {
  let best: MeshAnchor | null = null,
    score = Infinity;
  mesh.triangles.forEach(([ia, ib, ic], triangle) => {
    const a = frame.landmarks[ia],
      b = frame.landmarks[ib],
      c = frame.landmarks[ic];
    const det = (b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y);
    if (Math.abs(det) < 1e-10) return;
    const v = ((p.x - a.x) * (c.y - a.y) - (c.x - a.x) * (p.y - a.y)) / det;
    const w = ((b.x - a.x) * (p.y - a.y) - (p.x - a.x) * (b.y - a.y)) / det;
    const bary: [number, number, number] = [1 - v - w, v, w];
    const outside = -Math.min(...bary);
    if (outside < score) {
      score = outside;
      best = { triangle, bary };
    }
  });
  return score <= 0.03 ? best : null;
}

/** 양쪽 눈썹은 독립적으로 검출한다. 라벨의 좌우 명칭 대신 실제 위치로 나눈다. */
export function fitDetectedBrows(
  mask: Uint8Array,
  size: number,
  crop: FaceCrop,
  frame: FaceFrame,
  mesh: FaceMesh,
): BrowDetection {
  const guides: GuideStep["guides"] = [],
    outlines: MeshAnchor[][] = [];
  for (const [inner, outer] of [
    [55, 46],
    [285, 276],
  ]) {
    const a = frame.landmarks[inner],
      b = frame.landmarks[outer];
    const ax = a.x * frame.imageSize.width,
      ay = a.y * frame.imageSize.height;
    const dx = (b.x - a.x) * frame.imageSize.width,
      dy = (b.y - a.y) * frame.imageSize.height;
    const length = Math.hypot(dx, dy),
      ux = dx / length,
      uy = dy / length;
    const nx = ux >= 0 ? uy : -uy,
      ny = -Math.abs(ux);
    if (length < 10) throw new Error("눈썹이 너무 작습니다. 조금 가까이 와 주세요.");
    const points: { s: number; h: number }[] = [];
    // 예측 중 눈썹 부근의 가장 큰 연결 성분만 남긴다.
    const region = new Uint8Array(mask.length);
    for (let y = 0; y < size; y++)
      for (let x = 0; x < size; x++) {
        const index = y * size + x;
        if (!mask[index]) continue;
        const px = crop.x + ((x + 0.5) * crop.size) / size - ax,
          py = crop.y + ((y + 0.5) * crop.size) / size - ay;
        const s = (px * ux + py * uy) / length,
          h = (px * nx + py * ny) / length;
        if (s > -0.3 && s < 1.3 && Math.abs(h) < 0.55) region[index] = 1;
      }
    let largest: number[] = [];
    for (let i = 0; i < region.length; i++) {
      if (!region[i]) continue;
      const stack = [i],
        component: number[] = [];
      region[i] = 0;
      while (stack.length) {
        const n = stack.pop()!;
        component.push(n);
        for (const next of [
          n - size,
          n + size,
          ...(n % size > 0 ? [n - 1] : []),
          ...(n % size < size - 1 ? [n + 1] : []),
        ]) {
          if (next >= 0 && next < region.length && region[next]) {
            region[next] = 0;
            stack.push(next);
          }
        }
      }
      if (component.length > largest.length) largest = component;
    }
    for (const n of largest) {
      const px = crop.x + (((n % size) + 0.5) * crop.size) / size - ax,
        py = crop.y + ((Math.floor(n / size) + 0.5) * crop.size) / size - ay;
      points.push({ s: (px * ux + py * uy) / length, h: (px * nx + py * ny) / length });
    }
    if (points.length < 30)
      throw new Error("양쪽 눈썹을 충분히 찾지 못했습니다. 정면에서 다시 인식해 주세요.");
    points.sort((p, q) => p.s - q.s);
    const lo = points[Math.floor(points.length * 0.02)].s,
      hi = points[Math.floor(points.length * 0.98)].s;
    if (hi - lo < 0.5 || hi - lo > 1.6)
      throw new Error("눈썹 검출 범위가 불안정합니다. 정면에서 다시 인식해 주세요.");
    const bins = Array.from({ length: 24 }, () => [] as number[]);
    points.forEach((p) => {
      const k = Math.floor(((p.s - lo) / (hi - lo)) * 24);
      if (k >= 0 && k < 24) bins[k].push(p.h);
    });
    const curve = bins.map((values, k) => {
      values.sort((p, q) => p - q);
      return values.length >= 2
        ? {
            s: lo + ((k + 0.5) / 24) * (hi - lo),
            lower: values[Math.floor(values.length * 0.08)],
            upper: values[Math.floor(values.length * 0.92)],
          }
        : null;
    });
    if (curve.filter(Boolean).length < 18)
      throw new Error("눈썹 경계가 끊겨 있습니다. 조명과 앞머리를 확인해 주세요.");
    const valid = curve.filter((p): p is NonNullable<typeof p> => p !== null);
    const sample = (s: number) => {
      const k = Math.max(0, Math.min(valid.length - 2, valid.findIndex((p) => p.s >= s) - 1));
      const left = s >= valid[valid.length - 1].s ? valid[valid.length - 2] : valid[k];
      const right = s >= valid[valid.length - 1].s ? valid[valid.length - 1] : valid[k + 1];
      const t = Math.max(0, Math.min(1, (s - left.s) / (right.s - left.s)));
      return {
        lower: left.lower + (right.lower - left.lower) * t,
        upper: left.upper + (right.upper - left.upper) * t,
      };
    };
    const at = (s: number, h: number) =>
      imageAnchor(
        {
          x: (ax + length * (s * ux + h * nx)) / frame.imageSize.width,
          y: (ay + length * (s * uy + h * ny)) / frame.imageSize.height,
        },
        frame,
        mesh,
      );
    const edge = valid
      .map((p) => at(p.s, p.lower))
      .concat([...valid].reverse().map((p) => at(p.s, p.upper)));
    if (edge.some((p) => !p))
      throw new Error("눈썹을 얼굴 메시에 붙이지 못했습니다. 정면에서 다시 인식해 주세요.");
    outlines.push(edge as MeshAnchor[]);
    for (let k = 0; k < 40; k++) {
      // 중앙은 숱을 늘리고 앞머리·꼬리는 줄인다. 검출한 눈썹의 높이·곡률을 그대로 따라간다.
      const u = (k + 0.5) / 40,
        t = 0.5 + Math.asin(2 * u - 1) / Math.PI;
      const s = lo + (hi - lo) * (0.04 + 0.92 * t),
        end = Math.min(hi, s + (hi - lo) * (0.02 + 0.045 * t));
      const start = sample(s),
        finish = sample(end),
        mid = sample((s + end) / 2);
      const root = k % 2 === 0 ? 0.12 : 0.36,
        tip = Math.min(0.9, root + 0.5);
      const h = (p: typeof start, f: number) => p.lower + (p.upper - p.lower) * f;
      const path = [
        at(s, h(start, root)),
        at((s + end) / 2, h(mid, (root + tip) / 2)),
        at(end, h(finish, tip)),
      ];
      if (path.every((p) => p))
        guides.push({ type: "polyline", brush: true, width: 0.013, path: path as MeshAnchor[] });
    }
  }
  return {
    step: {
      stepId: "brow",
      order: 1,
      title: "눈썹: 실제 눈썹의 빈 곳을 결대로 채워요",
      regions: ["rightBrow", "leftBrow"],
      source: "template",
      guides,
    },
    outline: outlines,
  };
}
