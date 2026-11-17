import { GRID, MEASURED } from "@/domain/gauge/spec";

/** 얼굴 지도를 반으로 나눈 구역별 가린 몫(0~1). 왼쪽 · 오른쪽은 얼굴 기준이다 */
export interface ZoneCovers {
  whole: number;
  left: number;
  right: number;
  upper: number;
  lower: number;
}

/** 칸별 가린 몫에서, 재는 칸(MEASURED)만 모아 전체 · 좌우 · 위아래 구역의 평균을 낸다 */
export function zoneCovers(cellCover: Float32Array): ZoneCovers {
  const sum = { whole: 0, left: 0, right: 0, upper: 0, lower: 0 };
  const n = { whole: 0, left: 0, right: 0, upper: 0, lower: 0 };
  const add = (zone: keyof ZoneCovers, value: number) => {
    sum[zone] += value;
    n[zone]++;
  };
  for (let k = 0; k < GRID * GRID; k++) {
    if (!MEASURED[k]) continue;
    const row = Math.floor(k / GRID);
    const col = k % GRID;
    add("whole", cellCover[k]);
    add(col < GRID / 2 ? "left" : "right", cellCover[k]);
    add(row < GRID / 2 ? "upper" : "lower", cellCover[k]);
  }
  const mean = (zone: keyof ZoneCovers) => (n[zone] ? sum[zone] / n[zone] : 0);
  return {
    whole: mean("whole"),
    left: mean("left"),
    right: mean("right"),
    upper: mean("upper"),
    lower: mean("lower"),
  };
}

/** 네 구역 가운데 가장 많이 가린 구역의 몫. 손이 얼굴 한쪽만 가려도 드러난다 */
export const maxZone = (zones: ZoneCovers) =>
  Math.max(zones.left, zones.right, zones.upper, zones.lower);
