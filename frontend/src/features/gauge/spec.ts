// 기준 잡기 값과 칸 표는 AI(Python)와 같이 쓰도록 shared/gauge/baseline.v1.json에 둔다.
import raw from "../../../../shared/gauge/baseline.v1.json" with { type: "json" };

export const GRID: number = raw.grid;
export const FRAMES = raw.frames;
export const LIGHT = raw.light;
/** 칸 안 표본 중 이 비율 넘게 읽혀야 그 칸 색을 낸다 */
export const SHARE_MIN: number = raw.cells.shareMin;

/** 줄 i의 j번째 글자가 1이면 쓰는 칸이다. 칸 번호는 i × GRID + j */
function cellMask(rows: string[]): Uint8Array {
  const out = new Uint8Array(GRID * GRID);
  rows.forEach((row, i) => {
    for (let j = 0; j < GRID; j++) out[i * GRID + j] = row.charCodeAt(j) === 49 ? 1 : 0;
  });
  return out;
}

/** 색을 재는 칸. 얼굴 안에서 두 눈 구멍을 뺐다 */
export const MEASURED = cellMask(raw.cells.measured);
/** 맨피부 칸. 조명 변화를 잴 때 쓴다 */
export const SKIN = cellMask(raw.cells.skin);
