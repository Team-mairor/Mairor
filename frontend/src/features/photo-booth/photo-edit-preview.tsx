"use client";

import { useEffect, useRef, useState } from "react";

import { MAX_PHOTO_ZOOM, type PhotoPlacement } from "./crop";
import { createPhotoJpegBlob, createPhotoJpegFilename, PhotoJpegError } from "./export-jpeg";
import { BASIC_PHOTO_FRAME, type PhotoSlotId } from "./frame";
import { renderPhotoFrame, type FramePhotos } from "./render";

type CapturedPhotos = Record<PhotoSlotId, Blob>;
type PhotoPlacements = Partial<Record<PhotoSlotId, PhotoPlacement>>;
type PreviewMode = "edit" | "review";

const SLOT_IDS = BASIC_PHOTO_FRAME.slots.map((slot) => slot.id);

function photosWithPlacements(images: FramePhotos, placements: PhotoPlacements): FramePhotos {
  return {
    "slot-1": { image: images["slot-1"].image, placement: placements["slot-1"] },
    "slot-2": { image: images["slot-2"].image, placement: placements["slot-2"] },
    "slot-3": { image: images["slot-3"].image, placement: placements["slot-3"] },
    "slot-4": { image: images["slot-4"].image, placement: placements["slot-4"] },
  };
}

export function PhotoEditPreview({
  photos,
  onBack,
}: {
  photos: CapturedPhotos;
  onBack: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [images, setImages] = useState<FramePhotos | null>(null);
  const [decodeError, setDecodeError] = useState(false);
  const [renderError, setRenderError] = useState(false);
  const [placements, setPlacements] = useState<PhotoPlacements>({});
  const [renderedSignature, setRenderedSignature] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<PhotoSlotId>(SLOT_IDS[0]);
  const [mode, setMode] = useState<PreviewMode>("edit");
  const [downloadPending, setDownloadPending] = useState(false);
  const [downloadMessage, setDownloadMessage] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState(false);
  const downloadTimersRef = useRef(new Map<string, number>());
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    const downloadTimers = downloadTimersRef.current;
    return () => {
      mountedRef.current = false;
      for (const [url, timer] of downloadTimers) {
        window.clearTimeout(timer);
        URL.revokeObjectURL(url);
      }
      downloadTimers.clear();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let bitmaps: ImageBitmap[] = [];

    const decodePhotos = async () => {
      try {
        const decoded = await Promise.all(
          SLOT_IDS.map(async (id) => [id, await createImageBitmap(photos[id])] as const),
        );
        bitmaps = decoded.map(([, bitmap]) => bitmap);
        if (cancelled) {
          bitmaps.forEach((bitmap) => bitmap.close());
          return;
        }
        const bitmapBySlot = new Map(decoded);
        setImages({
          "slot-1": { image: bitmapBySlot.get("slot-1")! },
          "slot-2": { image: bitmapBySlot.get("slot-2")! },
          "slot-3": { image: bitmapBySlot.get("slot-3")! },
          "slot-4": { image: bitmapBySlot.get("slot-4")! },
        });
      } catch {
        if (!cancelled) setDecodeError(true);
      }
    };

    void decodePhotos();
    return () => {
      cancelled = true;
      bitmaps.forEach((bitmap) => bitmap.close());
    };
  }, [photos]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !images) return;
    const signature = JSON.stringify(placements);
    const frame = window.requestAnimationFrame(() => {
      try {
        renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, photosWithPlacements(images, placements));
        setRenderedSignature(signature);
        setRenderError(false);
      } catch {
        setRenderError(true);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [images, placements]);

  const download = async () => {
    const canvas = canvasRef.current;
    const currentSignature = JSON.stringify(placements);
    if (
      !canvas ||
      downloadPending ||
      !images ||
      renderError ||
      renderedSignature !== currentSignature
    ) {
      return;
    }

    setDownloadPending(true);
    setDownloadMessage(null);
    setDownloadError(false);
    let url: string | null = null;
    try {
      const blob = await createPhotoJpegBlob(canvas);
      if (!mountedRef.current) return;
      url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = createPhotoJpegFilename();
      anchor.hidden = true;
      document.body.appendChild(anchor);
      try {
        anchor.click();
      } finally {
        anchor.remove();
      }

      const objectUrl = url;
      const timer = window.setTimeout(() => {
        URL.revokeObjectURL(objectUrl);
        downloadTimersRef.current.delete(objectUrl);
      }, 1000);
      downloadTimersRef.current.set(objectUrl, timer);
      setDownloadMessage("JPG 다운로드를 시작했어요.");
    } catch (error) {
      if (url) URL.revokeObjectURL(url);
      if (mountedRef.current) {
        setDownloadError(true);
        setDownloadMessage(
          error instanceof PhotoJpegError
            ? error.message
            : "JPG 파일을 저장하지 못했어요. 다시 시도해 주세요.",
        );
      }
    } finally {
      if (mountedRef.current) setDownloadPending(false);
    }
  };

  const placement = placements[selectedSlot] ?? {};
  const updatePlacement = (change: PhotoPlacement) => {
    setRenderError(false);
    setPlacements((current) => ({
      ...current,
      [selectedSlot]: { ...current[selectedSlot], ...change },
    }));
  };

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 px-6 pt-5 pb-8">
      <header className="flex shrink-0 items-center justify-between">
        <button type="button" onClick={onBack} className="text-[17px] font-semibold text-navy">
          촬영 화면으로
        </button>
        <span className="text-[15px] font-semibold text-mute">
          {mode === "edit" ? "사진 편집" : "완성 미리보기"}
        </span>
      </header>

      {decodeError ? (
        <section
          role="alert"
          className="flex flex-1 flex-col items-center justify-center gap-3 text-center"
        >
          <h1 className="font-display text-[26px] text-ink">사진을 불러오지 못했어요</h1>
          <p className="text-[16px] text-mute">촬영 화면으로 돌아가 다시 시도해 주세요.</p>
          <button type="button" onClick={onBack} className="font-semibold text-navy">
            촬영 화면으로 돌아가기
          </button>
        </section>
      ) : (
        <section className="mx-auto flex w-full max-w-[680px] flex-1 flex-col gap-4 overflow-y-auto">
          <div className="relative flex min-h-[200px] flex-1 items-center justify-center">
            <canvas
              ref={canvasRef}
              aria-label="네 장의 사진이 들어간 합성 미리보기"
              className="h-auto max-h-[min(78dvh,900px)] w-auto max-w-full object-contain"
            />
            {!images && <p className="absolute text-mute">사진을 합치고 있어요</p>}
          </div>

          {renderError && (
            <p role="alert" className="text-center text-[15px] text-red-700">
              미리보기를 만들지 못했어요. 사진 편집을 계속하거나 다시 촬영해 주세요.
            </p>
          )}

          {mode === "edit" ? (
            <>
              <div className="grid grid-cols-4 gap-2" aria-label="편집할 사진 선택">
                {SLOT_IDS.map((id, index) => (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={selectedSlot === id}
                    onClick={() => setSelectedSlot(id)}
                    className={`h-12 rounded-xl border text-[15px] font-semibold ${selectedSlot === id ? "border-navy bg-ice text-navy" : "border-line bg-white text-mute"}`}
                  >
                    {index + 1}번 사진
                  </button>
                ))}
              </div>

              <div className="flex flex-col gap-3 rounded-2xl border border-line bg-white p-4">
                <label className="flex items-center justify-between gap-4 text-[15px] text-ink">
                  <span>확대 · {Number(placement.zoom ?? 1).toFixed(1)}×</span>
                  <input
                    aria-label={`${SLOT_IDS.indexOf(selectedSlot) + 1}번 사진 확대`}
                    type="range"
                    min="1"
                    max={MAX_PHOTO_ZOOM}
                    step="0.1"
                    value={placement.zoom ?? 1}
                    onChange={(event) => updatePlacement({ zoom: Number(event.target.value) })}
                    className="w-1/2 accent-navy"
                  />
                </label>
                <label className="flex items-center justify-between gap-4 text-[15px] text-ink">
                  <span>가로 위치</span>
                  <input
                    aria-label={`${SLOT_IDS.indexOf(selectedSlot) + 1}번 사진 가로 위치`}
                    type="range"
                    min="-1"
                    max="1"
                    step="0.01"
                    value={placement.panX ?? 0}
                    onChange={(event) => updatePlacement({ panX: Number(event.target.value) })}
                    className="w-1/2 accent-navy"
                  />
                </label>
                <label className="flex items-center justify-between gap-4 text-[15px] text-ink">
                  <span>세로 위치</span>
                  <input
                    aria-label={`${SLOT_IDS.indexOf(selectedSlot) + 1}번 사진 세로 위치`}
                    type="range"
                    min="-1"
                    max="1"
                    step="0.01"
                    value={placement.panY ?? 0}
                    onChange={(event) => updatePlacement({ panY: Number(event.target.value) })}
                    className="w-1/2 accent-navy"
                  />
                </label>
                <label className="flex items-center justify-between text-[15px] text-ink">
                  좌우 반전
                  <input
                    aria-label={`${SLOT_IDS.indexOf(selectedSlot) + 1}번 사진 좌우 반전`}
                    type="checkbox"
                    checked={placement.mirrored ?? false}
                    onChange={(event) => updatePlacement({ mirrored: event.target.checked })}
                    className="size-5 accent-navy"
                  />
                </label>
              </div>

              <button
                type="button"
                disabled={
                  !images || renderError || renderedSignature !== JSON.stringify(placements)
                }
                onClick={() => setMode("review")}
                className="flex h-14 shrink-0 items-center justify-center rounded-full bg-navy text-[17px] font-bold text-white disabled:opacity-50"
              >
                완성 미리보기 확인
              </button>
            </>
          ) : (
            <>
              <p
                role={downloadError ? "alert" : "status"}
                className={`text-center text-[16px] ${downloadError ? "text-red-700" : "text-mute"}`}
              >
                {downloadMessage ?? "네 컷 사진을 확인하고 JPG로 저장할 수 있어요."}
              </p>
              <button
                type="button"
                disabled={
                  !images ||
                  renderError ||
                  downloadPending ||
                  renderedSignature !== JSON.stringify(placements)
                }
                onClick={() => void download()}
                aria-busy={downloadPending}
                className="flex h-14 shrink-0 items-center justify-center rounded-full bg-navy text-[17px] font-bold text-white disabled:opacity-50"
              >
                {downloadPending ? "JPG 만드는 중" : "JPG 다운로드"}
              </button>
              <button
                type="button"
                onClick={() => setMode("edit")}
                className="flex h-14 shrink-0 items-center justify-center rounded-full border border-navy bg-white text-[17px] font-bold text-navy"
              >
                사진 수정하기
              </button>
            </>
          )}
        </section>
      )}
    </main>
  );
}
