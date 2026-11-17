import { describe, expect, it, vi } from "vitest";

import type { PhotoFrameTemplate } from "./frame";
import { renderPhotoFrame, type FramePhotos } from "./render";

/** 합성 순서·좌표 검사용 고정 프레임. 실제 프레임(overlay 필수)과 따로 둔다. */
const BASIC_PHOTO_FRAME = {
  id: "test-grid",
  version: 1,
  output: { width: 1200, height: 1800, background: "#ffffff" },
  slots: [
    { id: "slot-1", x: 60, y: 60, width: 520, height: 760 },
    { id: "slot-2", x: 620, y: 60, width: 520, height: 760 },
    { id: "slot-3", x: 60, y: 860, width: 520, height: 760 },
    { id: "slot-4", x: 620, y: 860, width: 520, height: 760 },
  ],
  brand: {
    text: "mairor",
    y: 1728,
    fontSize: 52,
    fontFamily: "Georgia, serif",
    color: "#1b2d63",
  },
} as const satisfies PhotoFrameTemplate;

function fixture() {
  let fillStyle = "";
  const stateStack: string[] = [];
  const ctx = {
    get fillStyle() {
      return fillStyle;
    },
    set fillStyle(value: string) {
      fillStyle = value;
    },
    fillRect: vi.fn(),
    fillText: vi.fn(),
    save: vi.fn(() => stateStack.push(fillStyle)),
    restore: vi.fn(() => {
      fillStyle = stateStack.pop() ?? "";
    }),
    translate: vi.fn(),
    scale: vi.fn(),
    drawImage: vi.fn(),
  };
  const canvas = {
    width: 10,
    height: 10,
    getContext: vi.fn(() => ctx),
  } as unknown as HTMLCanvasElement;
  const image = { width: 1600, height: 900 } as HTMLCanvasElement;
  const photos: FramePhotos = {
    "slot-1": { image },
    "slot-2": { image },
    "slot-3": { image },
    "slot-4": { image },
  };
  return { ctx, canvas, image, photos };
}

describe("네컷 Canvas 합성", () => {
  it("출력 크기와 배경을 설정하고 네 칸을 출력 좌표에 그린다", () => {
    const { ctx, canvas, image, photos } = fixture();
    renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, photos);
    expect([canvas.width, canvas.height]).toEqual([1200, 1800]);
    expect(ctx.fillStyle).toBe("#ffffff");
    expect(ctx.fillRect).toHaveBeenCalledWith(0, 0, 1200, 1800);
    expect(ctx.restore).toHaveBeenCalledTimes(5);
    expect(ctx.drawImage).toHaveBeenCalledTimes(4);
    expect(ctx.drawImage.mock.calls[0][0]).toBe(image);
    expect(ctx.translate.mock.calls).toEqual([
      [60, 60],
      [620, 60],
      [60, 860],
      [620, 860],
    ]);
    expect(ctx.scale).not.toHaveBeenCalled();
  });

  it("반전은 사진 칸 안에만 적용하고 다음 사진 전에 상태를 복원한다", () => {
    const { ctx, canvas, photos } = fixture();
    renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, {
      ...photos,
      "slot-1": { ...photos["slot-1"], placement: { mirrored: true } },
    });
    expect(ctx.translate.mock.calls[0]).toEqual([580, 60]);
    expect(ctx.scale).toHaveBeenCalledExactlyOnceWith(-1, 1);
    expect(ctx.restore).toHaveBeenCalledTimes(5);
  });

  it("브랜드 워드마크를 결과 이미지 하단 중앙에 그린다", () => {
    const { ctx, canvas, photos } = fixture();
    renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, photos);
    expect(ctx.fillText).toHaveBeenCalledExactlyOnceWith("mairor", 600, 1728);
    expect(ctx.fillStyle).toBe("#ffffff");
  });

  it("프레임 장식은 사진을 그린 다음 마지막에 그린다", () => {
    const { ctx, canvas, photos } = fixture();
    const overlay = { width: 1200, height: 1800 } as HTMLCanvasElement;
    renderPhotoFrame(
      canvas,
      { ...BASIC_PHOTO_FRAME, overlaySrc: "/frames/test.png" },
      photos,
      overlay,
    );
    expect(ctx.drawImage).toHaveBeenLastCalledWith(overlay, 0, 0, 1200, 1800);
  });

  it("잘못된 입력은 기존 미리보기를 지우기 전에 거부한다", () => {
    const { canvas, photos } = fixture();
    const image = { width: 0, height: 0 } as HTMLCanvasElement;
    expect(() =>
      renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, { ...photos, "slot-4": { image } }),
    ).toThrow();
    expect([canvas.width, canvas.height]).toEqual([10, 10]);
  });

  it("잘못된 크기의 overlay와 누락된 사진을 거부한다", () => {
    const { canvas, photos } = fixture();
    expect(() =>
      renderPhotoFrame(canvas, { ...BASIC_PHOTO_FRAME, overlaySrc: "/frame.png" }, photos, {
        width: 10,
        height: 10,
      } as HTMLCanvasElement),
    ).toThrow();
    expect(() => renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, {} as FramePhotos)).toThrow();
  });

  it("출력 canvas를 입력 사진으로 사용하는 것을 거부한다", () => {
    const { canvas, photos } = fixture();
    expect(() =>
      renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, { ...photos, "slot-1": { image: canvas } }),
    ).toThrow();
  });

  it("그리기에 실패해도 Canvas 상태를 복원한다", () => {
    const { ctx, canvas, photos } = fixture();
    ctx.drawImage.mockImplementationOnce(() => {
      throw new Error("decode failed");
    });
    expect(() => renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, photos)).toThrow("decode failed");
    expect(ctx.restore).toHaveBeenCalledOnce();
  });
});
