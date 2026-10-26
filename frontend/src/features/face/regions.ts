import type { RegionName } from "./types";

export const RIGHT_IRIS_CENTER = 468;
export const LEFT_IRIS_CENTER = 473;

interface RegionDef {
  indices: readonly number[];
  /** 각도 기준 [시작, 끝] */
  axis: readonly [number, number];
  side: "left" | "right" | "center";
}

export const REGIONS: Record<RegionName, RegionDef> = {
  rightEye: {
    indices: [33, 246, 161, 160, 159, 158, 157, 173, 133, 7, 163, 144, 145, 153, 154, 155],
    axis: [133, 33],
    side: "right",
  },
  leftEye: {
    indices: [263, 466, 388, 387, 386, 385, 384, 398, 362, 249, 390, 373, 374, 380, 381, 382],
    axis: [362, 263],
    side: "left",
  },
  rightBrow: {
    indices: [46, 53, 52, 65, 55, 70, 63, 105, 66, 107],
    axis: [55, 46],
    side: "right",
  },
  leftBrow: {
    indices: [276, 283, 282, 295, 285, 300, 293, 334, 296, 336],
    axis: [285, 276],
    side: "left",
  },
  lipsOuter: {
    indices: [
      61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 146, 91, 181, 84, 17, 314, 405, 321, 375,
    ],
    axis: [61, 291],
    side: "center",
  },
  lipsInner: {
    indices: [
      78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 95, 88, 178, 87, 14, 317, 402, 318, 324,
    ],
    axis: [78, 308],
    side: "center",
  },
  // TODO: 후보값. 디버그 화면에서 실측 후 확정
  rightCheek: {
    indices: [117, 118, 101, 36, 50, 205, 207, 147, 123, 116],
    axis: [234, 454],
    side: "right",
  },
  leftCheek: {
    indices: [346, 347, 330, 266, 280, 425, 427, 376, 352, 345],
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
