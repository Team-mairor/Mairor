import { describe, expect, it, vi } from "vitest";

import {
  createPhotoJpegBlob,
  createPhotoJpegFilename,
  DEFAULT_PHOTO_JPEG_QUALITY,
  PhotoJpegError,
} from "./export-jpeg";

function canvas(width = 1200, height = 1800, toBlob = vi.fn()) {
  return { width, height, toBlob } as unknown as HTMLCanvasElement;
}

describe("네 컷 JPG 내보내기", () => {
  it("기본 화질로 합성 Canvas를 JPEG Blob으로 바꾼다", async () => {
    const blob = new Blob(["jpeg"], { type: "image/jpeg" });
    const toBlob = vi.fn((callback: BlobCallback) => callback(blob));

    await expect(createPhotoJpegBlob(canvas(1200, 1800, toBlob))).resolves.toBe(blob);
    expect(toBlob).toHaveBeenCalledWith(
      expect.any(Function),
      "image/jpeg",
      DEFAULT_PHOTO_JPEG_QUALITY,
    );
  });

  it.each([
    ["null 결과", null],
    ["빈 결과", new Blob([], { type: "image/jpeg" })],
    ["JPEG가 아닌 결과", new Blob(["png"], { type: "image/png" })],
  ])("%s는 인코딩 오류로 거부한다", async (_label, result) => {
    const toBlob = vi.fn((callback: BlobCallback) => callback(result));

    await expect(createPhotoJpegBlob(canvas(1200, 1800, toBlob))).rejects.toMatchObject({
      name: "PhotoJpegError",
      kind: "encoding-failed",
    });
  });

  it("출력 크기가 없거나 화질 범위가 잘못되면 인코더를 호출하지 않는다", async () => {
    const toBlob = vi.fn();

    await expect(createPhotoJpegBlob(canvas(0, 1800, toBlob))).rejects.toBeInstanceOf(
      PhotoJpegError,
    );
    await expect(createPhotoJpegBlob(canvas(1200, 1800, toBlob), 1.1)).rejects.toMatchObject({
      kind: "invalid-quality",
    });
    expect(toBlob).not.toHaveBeenCalled();
  });

  it("toBlob에서 발생한 동기 오류를 재시도 가능한 내보내기 오류로 바꾼다", async () => {
    const toBlob = vi.fn(() => {
      throw new DOMException("tainted canvas", "SecurityError");
    });

    await expect(createPhotoJpegBlob(canvas(1200, 1800, toBlob))).rejects.toMatchObject({
      name: "PhotoJpegError",
      kind: "encoding-failed",
    });
  });

  it("로컬 날짜·시간으로 JPG 파일 이름을 만든다", () => {
    expect(createPhotoJpegFilename(new Date(2026, 0, 2, 3, 4, 5))).toBe(
      "mairor-4cut-20260102-030405.jpg",
    );
    expect(() => createPhotoJpegFilename(new Date(Number.NaN))).toThrow(RangeError);
  });
});
