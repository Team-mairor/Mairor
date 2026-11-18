/** 촬영 순서와 프레임 영역을 연결하는 ID. 프레임 변경 시에도 사진 순서를 유지한다. */
export type PhotoSlotId = "slot-1" | "slot-2" | "slot-3" | "slot-4";

/** 좌표·크기는 CSS 픽셀이 아니라 최종 출력 이미지의 픽셀 단위다. */
export interface PhotoSlot {
  readonly id: PhotoSlotId;
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface PhotoFrameTemplate {
  readonly id: string;
  /** 좌표·출력 규격 변경 시 증가시킨다. */
  readonly version: number;
  readonly output: {
    readonly width: number;
    readonly height: number;
    /** JPEG의 투명 영역을 방지하는 불투명 #RRGGBB 배경색. */
    readonly background: string;
  };
  /** slot-1~slot-4 순서로 정의한다. 영역은 출력 범위 내에서 겹치지 않아야 한다. */
  readonly slots: readonly [PhotoSlot, PhotoSlot, PhotoSlot, PhotoSlot];
  /** JPEG 하단 여백에 출력할 브랜드 워드마크. */
  readonly brand?: {
    readonly text: string;
    readonly y: number;
    readonly fontSize: number;
    readonly fontFamily: string;
    readonly color: string;
  };
  /**
   * 디자이너가 제공할 선택적 투명 프레임 이미지의 same-origin 경로.
   * 출력 크기 전체에 배치한다. 배경 → 사진 네 장 → overlay 순으로 합성한다.
   * 이미지의 사진 영역은 slots의 좌표와 일치해야 한다.
   */
  readonly overlaySrc?: string;
}

/**
 * SSAFY 15기 기념 네컷 프레임. 1800×2646, 사진 칸은 825×1100(정확한 3:4).
 * overlay는 디자이너의 검은 프레임 사진 칸을 투명하게 뚫고, 칸마다 함께 찍는 사람과 흰 문구를 붙인 이미지다(일반 모드).
 * 칸 위치는 프레임 구멍(822×1097)을 잰 값이고, 크기는 구멍보다 3px 크게 잡아 프레임이 가장자리를 덮는다.
 * 칸 비율이 작은 정수비가 아니면 촬영 시 카메라 영상이 크게 잘려 확대되므로(capture-crop) 3:4를 지킨다.
 */
export const BASIC_PHOTO_FRAME = {
  id: "ssafy15",
  version: 3,
  output: { width: 1800, height: 2646, background: "#ffffff" },
  slots: [
    { id: "slot-1", x: 48, y: 48, width: 825, height: 1100 },
    { id: "slot-2", x: 48, y: 1193, width: 825, height: 1100 },
    { id: "slot-3", x: 930, y: 271, width: 825, height: 1100 },
    { id: "slot-4", x: 930, y: 1416, width: 825, height: 1100 },
  ],
  overlaySrc: "/images/photo/ssafy-final-overlay.png",
} as const satisfies PhotoFrameTemplate;

/** 미러필름 모드(<html class="mirror">)에서 쓰는 프레임. 검은 화면 위에서 보이도록 #f4f9ff 바탕·네이비 문구이고, 칸 좌표는 BASIC_PHOTO_FRAME과 같다. */
export const MIRROR_FRAME_OVERLAY_SRC = "/images/photo/ssafy-final-overlay-mirror.png";
