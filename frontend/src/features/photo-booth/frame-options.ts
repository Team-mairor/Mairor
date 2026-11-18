import { BASIC_PHOTO_FRAME, MIRROR_FRAME_OVERLAY_SRC, type PhotoFrameTemplate } from "./frame";

export type PhotoFrameId = "ssafy15" | "white" | "black";

/** 촬영 화면에 겹쳐 보이는 함께 찍는 사람. 칸 아래쪽에 붙고, 크기는 원본 픽셀 값이다. */
export interface CaptureGuest {
  readonly src: string;
  readonly side: "left" | "right";
  readonly width: number;
  readonly height: number;
}

/** 프레임 선택 화면에 나오는 프레임 한 종류. 칸 배치와 사진 규격은 template이 정한다. */
export interface PhotoFrameOption {
  readonly id: PhotoFrameId;
  readonly name: string;
  readonly template: PhotoFrameTemplate;
  /** 미러필름 모드(<html class="mirror">)에서 합성에 쓰는 밝은 프레임 이미지 */
  readonly mirrorOverlaySrc?: string;
  /** 선택 화면 예시 이미지. 없으면 칸 배치를 그려 보여 준다 */
  readonly previewSrc?: string;
  readonly previewMirrorSrc?: string;
  /** 예시에 그리는 칸 색 */
  readonly previewSlotColor?: string;
  /** 컷 순서대로의 안내 이미지. 없으면 촬영 화면에 겹치지 않는다 */
  readonly guests?: readonly CaptureGuest[];
  /** guests 너비 계산의 기준이 되는 칸(프레임 구멍) 너비 */
  readonly guestHoleWidth?: number;
  /** 우측 하단 촬영 날짜·mairor 글씨 */
  readonly stamp: {
    readonly color: string;
    /** 미러필름 모드에서 쓰는 밝은 프레임 이미지 위의 글씨 색 */
    readonly mirrorColor?: string;
    /** false면 프레임 이미지에 mairor 글씨가 이미 있어 날짜만 그린다 */
    readonly mairor: boolean;
  };
}

/** 사진 없는 기본 프레임. 칸 배치는 SSAFY 15기 프레임과 같다. */
function plainFrame(id: string, background: string): PhotoFrameTemplate {
  return {
    id,
    version: 1,
    output: { ...BASIC_PHOTO_FRAME.output, background },
    slots: BASIC_PHOTO_FRAME.slots,
  };
}

export const PHOTO_FRAME_OPTIONS: readonly PhotoFrameOption[] = [
  {
    id: "ssafy15",
    name: "SSAFY 15기",
    template: BASIC_PHOTO_FRAME,
    mirrorOverlaySrc: MIRROR_FRAME_OVERLAY_SRC,
    previewSrc: "/images/photo/ssafy-final-frame.png",
    previewMirrorSrc: "/images/photo/ssafy-final-frame-mirror.png",
    guestHoleWidth: 822,
    stamp: { color: "#ffffff", mirrorColor: "#1b2d63", mairor: true },
    guests: [
      { src: "/images/photo/ssafy-final-guest-1.png", side: "left", width: 454, height: 1097 },
      { src: "/images/photo/ssafy-final-guest-2.png", side: "left", width: 489, height: 1012 },
      { src: "/images/photo/ssafy-final-guest-3.png", side: "right", width: 478, height: 970 },
      { src: "/images/photo/ssafy-final-guest-4.png", side: "right", width: 639, height: 988 },
    ],
  },
  {
    id: "white",
    name: "화이트",
    template: plainFrame("plain-white", "#ffffff"),
    previewSlotColor: "#dfe4ee",
    stamp: { color: "#0b1430", mairor: true },
  },
  {
    id: "black",
    name: "블랙",
    template: plainFrame("plain-black", "#111111"),
    previewSlotColor: "#3b4152",
    stamp: { color: "#ffffff", mairor: true },
  },
];

export function findPhotoFrameOption(id: string | null): PhotoFrameOption | undefined {
  return PHOTO_FRAME_OPTIONS.find((option) => option.id === id);
}
