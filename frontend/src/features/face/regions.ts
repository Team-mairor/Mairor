import type { RegionName } from "./types";

export const RIGHT_IRIS_CENTER = 468;
export const LEFT_IRIS_CENTER = 473;

interface RegionDef {
  /** 외곽선을 따라 한 바퀴 도는 순서. 그대로 이으면 닫힌 도형이 된다. */
  indices: readonly number[];
  /** 각도 기준 [시작, 끝] */
  axis: readonly [number, number];
  side: "left" | "right" | "center";
}

export const REGIONS: Record<RegionName, RegionDef> = {
  rightEye: {
    indices: [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7],
    axis: [133, 33],
    side: "right",
  },
  leftEye: {
    indices: [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249],
    axis: [362, 263],
    side: "left",
  },
  rightBrow: {
    indices: [46, 53, 52, 65, 55, 107, 66, 105, 63, 70],
    axis: [55, 46],
    side: "right",
  },
  leftBrow: {
    indices: [276, 283, 282, 295, 285, 336, 296, 334, 293, 300],
    axis: [285, 276],
    side: "left",
  },
  lipsOuter: {
    indices: [
      61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146,
    ],
    axis: [61, 291],
    side: "center",
  },
  lipsInner: {
    indices: [
      78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95,
    ],
    axis: [78, 308],
    side: "center",
  },
  // TODO: 후보값. 디버그 화면에서 실측 후 확정
  rightCheek: {
    indices: [123, 116, 117, 118, 101, 36, 50, 205, 207, 147],
    axis: [234, 454],
    side: "right",
  },
  leftCheek: {
    indices: [330, 347, 346, 345, 352, 376, 427, 425, 280, 266],
    axis: [234, 454],
    side: "left",
  },
  faceOval: {
    indices: [
      10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152,
      148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
    ],
    axis: [234, 454],
    side: "center",
  },
};

export const REGION_NAMES = Object.keys(REGIONS) as RegionName[];

/** 부위 이름 목록이 아니면 이유를 돌려준다. 없는 이름이 하나라도 있으면 그리는 중에 오류가 난다. */
export function regionNamesError(names: unknown, { allowEmpty = false } = {}): string | null {
  if (!Array.isArray(names)) return "부위 목록이 배열이 아닙니다";
  if (!allowEmpty && names.length === 0) return "부위 목록이 비어 있습니다";
  const unknown = names.find((name) => !(REGION_NAMES as unknown[]).includes(name));
  return unknown === undefined ? null : `없는 부위 이름입니다: ${String(unknown)}`;
}
