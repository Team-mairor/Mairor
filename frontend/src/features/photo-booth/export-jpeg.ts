/** 기본 프레임 1200×1800 합성 결과를 기기에서 저장할 JPEG로 변환한다. */
export const DEFAULT_PHOTO_JPEG_QUALITY = 0.92;

/** 로컬 날짜·시간으로 저장 파일 이름을 만든다. */
export function createPhotoJpegFilename(date = new Date()): string {
  if (!Number.isFinite(date.getTime())) {
    throw new RangeError("파일 이름에 사용할 날짜가 올바르지 않아요.");
  }
  const pad = (value: number) => String(value).padStart(2, "0");
  const timestamp = [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    "-",
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join("");
  return `mairor-4cut-${timestamp}.jpg`;
}

export type PhotoJpegErrorKind = "invalid-canvas" | "invalid-quality" | "encoding-failed";

export class PhotoJpegError extends Error {
  constructor(
    readonly kind: PhotoJpegErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "PhotoJpegError";
  }
}

/** 합성된 Canvas를 JPEG Blob으로 인코딩한다. 다운로드와 파일명 처리는 호출자가 담당한다. */
export function createPhotoJpegBlob(
  canvas: HTMLCanvasElement,
  quality = DEFAULT_PHOTO_JPEG_QUALITY,
): Promise<Blob> {
  if (
    !Number.isSafeInteger(canvas.width) ||
    canvas.width <= 0 ||
    !Number.isSafeInteger(canvas.height) ||
    canvas.height <= 0
  ) {
    return Promise.reject(
      new PhotoJpegError("invalid-canvas", "합성된 사진 크기를 확인할 수 없어요."),
    );
  }
  if (!Number.isFinite(quality) || quality < 0 || quality > 1) {
    return Promise.reject(
      new PhotoJpegError("invalid-quality", "JPG 화질 설정이 올바르지 않아요."),
    );
  }

  return new Promise((resolve, reject) => {
    try {
      canvas.toBlob(
        (blob) => {
          if (!blob || blob.size === 0 || blob.type !== "image/jpeg") {
            reject(new PhotoJpegError("encoding-failed", "JPG 파일을 만들지 못했어요."));
            return;
          }
          resolve(blob);
        },
        "image/jpeg",
        quality,
      );
    } catch {
      reject(new PhotoJpegError("encoding-failed", "JPG 파일을 만들지 못했어요."));
    }
  });
}
