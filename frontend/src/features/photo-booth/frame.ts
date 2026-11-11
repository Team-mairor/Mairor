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
  /**
   * 디자이너가 제공할 선택적 투명 프레임 이미지의 same-origin 경로.
   * 출력 크기 전체에 배치한다. 배경 → 사진 네 장 → overlay 순으로 합성한다.
   * 이미지의 사진 영역은 slots의 좌표와 일치해야 한다.
   */
  readonly overlaySrc?: string;
}

/**
 * 촬영·합성 개발용 2×2 프레임. 최종 디자인은 최주연 담당이다.
 * 1200×1800은 개발 기준값이며 사진/프레임 규격을 확정한 뒤 교체할 수 있다.
 * 장식·문구·브랜드 요소는 이 기본 데이터에 포함하지 않는다.
 */
export const BASIC_PHOTO_FRAME = {
  id: "basic-grid",
  version: 1,
  output: { width: 1200, height: 1800, background: "#ffffff" },
  slots: [
    { id: "slot-1", x: 60, y: 60, width: 520, height: 760 },
    { id: "slot-2", x: 620, y: 60, width: 520, height: 760 },
    { id: "slot-3", x: 60, y: 860, width: 520, height: 760 },
    { id: "slot-4", x: 620, y: 860, width: 520, height: 760 },
  ],
} as const satisfies PhotoFrameTemplate;
