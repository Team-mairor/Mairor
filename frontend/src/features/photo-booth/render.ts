import { calculatePhotoCrop, type PhotoPlacement } from "./crop";
import type { PhotoFrameTemplate, PhotoSlotId } from "./frame";
import { assertPhotoFrame } from "./validate-frame";

/** 호출자가 디코딩을 완료하고 수명을 관리하는 이미지. */
export type PhotoImage = HTMLImageElement | HTMLCanvasElement | ImageBitmap | OffscreenCanvas;

export interface FramePhoto {
  readonly image: PhotoImage;
  readonly placement?: PhotoPlacement;
}

export type FramePhotos = Readonly<Record<PhotoSlotId, FramePhoto>>;

function imageSize(image: PhotoImage) {
  return "naturalWidth" in image
    ? { width: image.naturalWidth, height: image.naturalHeight }
    : { width: image.width, height: image.height };
}

/**
 * 미리보기와 JPG 출력이 함께 사용하는 브라우저 Canvas 합성 함수.
 * 디코딩된 사진 네 장을 받아 출력 크기로 그린다. 이미지 로드·파일 저장은 호출자 책임이다.
 * 입력 검증이 끝나기 전에는 기존 canvas를 변경하지 않는다.
 */
export function renderPhotoFrame(
  canvas: HTMLCanvasElement,
  frame: PhotoFrameTemplate,
  photos: FramePhotos,
  overlay?: PhotoImage,
): void {
  assertPhotoFrame(frame);
  if (Boolean(frame.overlaySrc) !== Boolean(overlay)) {
    throw new Error("프레임 이미지 설정에 맞는 디코딩된 overlay가 필요합니다.");
  }
  if (overlay) {
    const size = imageSize(overlay);
    if (
      overlay === canvas ||
      size.width !== frame.output.width ||
      size.height !== frame.output.height
    ) {
      throw new Error("프레임 이미지는 출력 크기와 같아야 하며 출력 canvas와 달라야 합니다.");
    }
  }
  const prepared = frame.slots.map((slot) => {
    const photo = photos[slot.id];
    if (!photo || photo.image === canvas) {
      throw new Error("각 사진 영역에 출력 canvas와 다른 이미지가 필요합니다.");
    }
    return { slot, photo, crop: calculatePhotoCrop(imageSize(photo.image), slot, photo.placement) };
  });
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("사진 합성을 위한 Canvas를 만들 수 없습니다.");

  canvas.width = frame.output.width;
  canvas.height = frame.output.height;
  ctx.fillStyle = frame.output.background;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (const { slot, photo, crop } of prepared) {
    ctx.save();
    try {
      ctx.translate(slot.x + (crop.mirrored ? slot.width : 0), slot.y);
      if (crop.mirrored) ctx.scale(-1, 1);
      ctx.drawImage(
        photo.image,
        crop.x,
        crop.y,
        crop.width,
        crop.height,
        0,
        0,
        slot.width,
        slot.height,
      );
    } finally {
      ctx.restore();
    }
  }
  if (overlay) ctx.drawImage(overlay, 0, 0, canvas.width, canvas.height);
  if (frame.brand) {
    ctx.save();
    try {
      ctx.fillStyle = frame.brand.color;
      ctx.font = `italic ${frame.brand.fontSize}px ${frame.brand.fontFamily}`;
      ctx.textAlign = "center";
      ctx.textBaseline = "alphabetic";
      ctx.fillText(frame.brand.text, canvas.width / 2, frame.brand.y);
    } finally {
      ctx.restore();
    }
  }
}
