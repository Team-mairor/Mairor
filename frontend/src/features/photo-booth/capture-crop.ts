import type { PhotoSize } from "./crop";

export interface PhotoCaptureCrop extends PhotoSize {
  readonly x: number;
  readonly y: number;
}

function greatestCommonDivisor(left: number, right: number): number {
  let a = left;
  let b = right;
  while (b !== 0) [a, b] = [b, a % b];
  return a;
}

/** Center-crops camera pixels to an exact integer multiple of the selected frame slot ratio. */
export function calculatePhotoCaptureCrop(source: PhotoSize, slot: PhotoSize): PhotoCaptureCrop {
  if (
    !Number.isSafeInteger(source.width) ||
    !Number.isSafeInteger(source.height) ||
    !Number.isSafeInteger(slot.width) ||
    !Number.isSafeInteger(slot.height) ||
    source.width <= 0 ||
    source.height <= 0 ||
    slot.width <= 0 ||
    slot.height <= 0
  ) {
    throw new RangeError("카메라와 사진 영역 크기는 양의 정수여야 합니다.");
  }

  const divisor = greatestCommonDivisor(slot.width, slot.height);
  const unitWidth = slot.width / divisor;
  const unitHeight = slot.height / divisor;
  const units = Math.floor(Math.min(source.width / unitWidth, source.height / unitHeight));
  if (units < 1) throw new RangeError("카메라 영상이 사진 영역보다 작습니다.");

  const width = unitWidth * units;
  const height = unitHeight * units;
  return {
    x: Math.floor((source.width - width) / 2),
    y: Math.floor((source.height - height) / 2),
    width,
    height,
  };
}
