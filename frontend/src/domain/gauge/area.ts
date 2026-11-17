import type { MeshAnchor } from "@/vision/face";
import type { AreaGuideSet } from "@/vision/guide";
import type { FaceMesh } from "@/vision/overlay";

import { GRID, MEASURED } from "./spec";
import measure from "../../../../shared/gauge/measure.v1.json" with { type: "json" };

/** 칸 하나를 SUB × SUB 점으로 나눠 테두리 안 몫을 잰다. AI는 칸마다 8 × 8 지도 픽셀이다 */
const SUB = 8;
const SIDE = GRID * SUB;

type Pt = [number, number];

const uvOf = ({ triangle, bary }: MeshAnchor, mesh: FaceMesh): Pt => {
  const [a, b, c] = mesh.triangles[triangle].map((i) => mesh.uv[i]);
  return [
    a[0] * bary[0] + b[0] * bary[1] + c[0] * bary[2],
    a[1] * bary[0] + b[1] * bary[1] + c[1] * bary[2],
  ];
};

/** 점이 테두리 안인지(짝홀 규칙) */
export function insidePolygon(poly: Pt[], x: number, y: number): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** UV 테두리들을 SIDE × SIDE 점으로 칠해, 점마다 콜백을 부른다 */
function fill(polys: Pt[][], visit: (x: number, y: number) => void) {
  for (const poly of polys) {
    const xs = poly.map((p) => p[0] * SIDE - 0.5);
    const ys = poly.map((p) => p[1] * SIDE - 0.5);
    const x0 = Math.max(0, Math.ceil(Math.min(...xs)));
    const x1 = Math.min(SIDE - 1, Math.floor(Math.max(...xs)));
    const y0 = Math.max(0, Math.ceil(Math.min(...ys)));
    const y1 = Math.min(SIDE - 1, Math.floor(Math.max(...ys)));
    for (let y = y0; y <= y1; y++)
      for (let x = x0; x <= x1; x++)
        if (insidePolygon(poly, (x + 0.5) / SIDE, (y + 0.5) / SIDE)) visit(x, y);
  }
}

/**
 * 영역 묶음 테두리를 칸 표로 옮긴다. 테두리 안이 칸의 area.share 이상이고 재는 칸인 칸이다.
 * 한 묶음의 도형끼리 겹친 점은 한 번만 센다
 */
export function areaCells(set: AreaGuideSet, mesh: FaceMesh): Uint8Array {
  const polys = set.guides
    .filter((g) => g.type === "polygon")
    .map((g) => g.outline.map((a) => uvOf(a, mesh)));
  const hit = new Uint8Array(SIDE * SIDE);
  fill(polys, (x, y) => (hit[y * SIDE + x] = 1));
  const count = new Uint16Array(GRID * GRID);
  for (let y = 0; y < SIDE; y++)
    for (let x = 0; x < SIDE; x++)
      if (hit[y * SIDE + x]) count[Math.floor(y / SUB) * GRID + Math.floor(x / SUB)]++;
  const out = new Uint8Array(GRID * GRID);
  for (let k = 0; k < out.length; k++)
    out[k] = MEASURED[k] && count[k] >= measure.area.share * SUB * SUB ? 1 : 0;
  return out;
}

/** 그 단계 모든 영역 칸. 조명 재기에서 뺀다 */
export function madeCells(areas: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(GRID * GRID);
  for (const cells of areas) for (let k = 0; k < out.length; k++) out[k] |= cells[k];
  return out;
}

/** UV 테두리 안의 지도 점(SIDE × SIDE 격자의 픽셀 가운데) */
export function polygonPoints(polys: Pt[][]): Pt[] {
  const seen = new Set<number>();
  const out: Pt[] = [];
  fill(polys, (x, y) => {
    const k = y * SIDE + x;
    if (seen.has(k)) return;
    seen.add(k);
    out.push([(x + 0.5) / SIDE, (y + 0.5) / SIDE]);
  });
  return out;
}
