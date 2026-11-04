import type { GuideShape } from "@/features/face";
import type { FaceMesh } from "@/features/overlay";

/** 얼굴 지도(UV)에서 이 두께보다 얇은 영역을 얇은 띠로 본다. 아이라인 띠는 약 0.006, 애교살 띠는 약 0.03 */
export const THIN_AREA_UV = 0.015;

const thinCache = new WeakMap<GuideShape, boolean>();

/**
 * 아이라인처럼 얇은 띠 영역인지. 얼굴 지도(UV)에서 평균 두께(넓이 × 2 / 둘레)로 잰다.
 * 화면 두께로 재면 고개 각도에 따라 양쪽 눈 판정이 갈려 UV로 재고, 도형마다 한 번만 계산한다
 */
export function isThinArea(guide: GuideShape, mesh: FaceMesh): boolean {
  if (guide.type !== "polygon") return false;
  const cached = thinCache.get(guide);
  if (cached !== undefined) return cached;
  const points = guide.outline.map(({ triangle, bary }) => {
    const [a, b, c] = mesh.triangles[triangle].map((i) => mesh.uv[i]);
    return [
      a[0] * bary[0] + b[0] * bary[1] + c[0] * bary[2],
      a[1] * bary[0] + b[1] * bary[1] + c[1] * bary[2],
    ];
  });
  let area = 0;
  let perimeter = 0;
  points.forEach(([x, y], i) => {
    const [nx, ny] = points[(i + 1) % points.length];
    area += x * ny - nx * y;
    perimeter += Math.hypot(nx - x, ny - y);
  });
  const thin = perimeter > 0 && Math.abs(area) / perimeter < THIN_AREA_UV;
  thinCache.set(guide, thin);
  return thin;
}
