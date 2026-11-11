export interface PhotoSize {
  readonly width: number;
  readonly height: number;
}

export interface PhotoPlacement {
  /** 슬롯을 채우는 최소 배율에 대한 배수. 1~4. */
  readonly zoom?: number;
  /** 화면에서 사진을 움직이는 방향. -1은 왼쪽/위, 1은 오른쪽/아래 끝이다. */
  readonly panX?: number;
  readonly panY?: number;
  readonly mirrored?: boolean;
}

/** 원본 이미지에서 잘라낼 영역. 화면·출력 크기와 관계없이 원본 픽셀 단위다. */
export interface PhotoCrop extends PhotoSize {
  readonly x: number;
  readonly y: number;
  /** 잘라낸 영역을 슬롯 안에서 좌우 반전한다. */
  readonly mirrored: boolean;
}

export const MAX_PHOTO_ZOOM = 4;

function positiveSize(size: PhotoSize) {
  if (![size.width, size.height].every((v) => Number.isFinite(v) && v > 0)) {
    throw new RangeError("사진과 슬롯의 크기는 유한한 양수여야 합니다.");
  }
}

function bounded(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) throw new RangeError("사진 배치 값은 유한한 숫자여야 합니다.");
  return Math.max(min, Math.min(max, value));
}

/**
 * cover 크롭: 원본 비율을 유지하고 슬롯 전체를 채운다.
 * 미리보기와 JPG 출력은 이 영역을 동일하게 잘라 슬롯 크기에 그린다.
 * 반전은 크롭 후 슬롯 내부에서 적용하며 pan은 항상 사용자가 보는 화면 방향이다.
 */
export function calculatePhotoCrop(
  image: PhotoSize,
  slot: PhotoSize,
  placement: PhotoPlacement = {},
): PhotoCrop {
  positiveSize(image);
  positiveSize(slot);
  const zoom = bounded(placement.zoom ?? 1, 1, MAX_PHOTO_ZOOM);
  const panX = bounded(placement.panX ?? 0, -1, 1);
  const panY = bounded(placement.panY ?? 0, -1, 1);
  const mirrored = placement.mirrored ?? false;
  const scale = Math.max(slot.width / image.width, slot.height / image.height);
  const width = Math.min(image.width, slot.width / scale / zoom);
  const height = Math.min(image.height, slot.height / scale / zoom);
  const remainingX = image.width - width;
  const remainingY = image.height - height;
  return {
    x: (remainingX * (1 - (mirrored ? -panX : panX))) / 2,
    y: (remainingY * (1 - panY)) / 2,
    width,
    height,
    mirrored,
  };
}
