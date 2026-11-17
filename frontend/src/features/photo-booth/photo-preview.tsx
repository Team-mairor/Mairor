"use client";

import { ChevronLeft, Clock, QrCode, RotateCw } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";

import { BottomTabs } from "@/components/bottom-tabs";
import { PillButton } from "@/components/ui/pill-button";
import { errorMessage } from "@/lib/api";

import { createPhotoJpegBlob, PhotoJpegError } from "./export-jpeg";
import { BASIC_PHOTO_FRAME, MIRROR_FRAME_OVERLAY_SRC, type PhotoSlotId } from "./frame";
import { renderPhotoFrame, type FramePhotos } from "./render";
import { createPhotoShare } from "./share-api";

type CapturedPhotos = Record<PhotoSlotId, Blob>;

const SLOT_IDS = BASIC_PHOTO_FRAME.slots.map((slot) => slot.id);
/** 촬영 화면은 거울처럼 좌우 반전해 보여 주므로, 결과도 본 모습 그대로 좌우 반전해 합성한다. */
const MIRRORED = { mirrored: true } as const;

/** 네 장을 프레임에 합성해 보여 주고 QR 공유로 저장한다. 위치·확대 조정 없이 촬영 그대로 쓴다. */
export function PhotoPreview({
  photos,
  onBack,
  onShared,
}: {
  photos: CapturedPhotos;
  onBack: () => void;
  /** QR 공유가 만들어졌을 때. 사진이 공유됐으므로 촬영 화면의 나가기 경고를 끈다. */
  onShared?: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [images, setImages] = useState<FramePhotos | null>(null);
  const [overlay, setOverlay] = useState<ImageBitmap | null>(null);
  const [decodeError, setDecodeError] = useState(false);
  const [renderError, setRenderError] = useState(false);
  const [rendered, setRendered] = useState(false);
  const [sharePending, setSharePending] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [share, setShare] = useState<{ url: string; expiresAt: string } | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let bitmaps: ImageBitmap[] = [];

    const decodePhotos = async () => {
      try {
        const [frameImage, decoded] = await Promise.all([
          // 일반 모드는 검은 프레임, 미러필름 모드는 밝은(#f4f9ff) 프레임을 쓴다. 칸 좌표는 같다
          fetch(
            document.documentElement.classList.contains("mirror")
              ? MIRROR_FRAME_OVERLAY_SRC
              : BASIC_PHOTO_FRAME.overlaySrc,
          )
            .then((response) => {
              if (!response.ok) throw new Error("프레임 이미지를 불러오지 못했어요.");
              return response.blob();
            })
            .then((blob) => createImageBitmap(blob)),
          Promise.all(
            SLOT_IDS.map(async (id) => [id, await createImageBitmap(photos[id])] as const),
          ),
        ]);
        bitmaps = [frameImage, ...decoded.map(([, bitmap]) => bitmap)];
        if (cancelled) {
          bitmaps.forEach((bitmap) => bitmap.close());
          return;
        }
        const bitmapBySlot = new Map(decoded);
        setOverlay(frameImage);
        setImages({
          "slot-1": { image: bitmapBySlot.get("slot-1")!, placement: MIRRORED },
          "slot-2": { image: bitmapBySlot.get("slot-2")!, placement: MIRRORED },
          "slot-3": { image: bitmapBySlot.get("slot-3")!, placement: MIRRORED },
          "slot-4": { image: bitmapBySlot.get("slot-4")!, placement: MIRRORED },
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
    if (!canvas || !images || !overlay) return;
    const frame = window.requestAnimationFrame(() => {
      try {
        renderPhotoFrame(canvas, BASIC_PHOTO_FRAME, images, overlay);
        setRendered(true);
      } catch {
        setRenderError(true);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [images, overlay]);

  /** 합성한 JPEG를 올려 만료되는 공유 주소를 받고, 휴대폰으로 찍을 QR을 띄운다. */
  const createShare = async () => {
    const canvas = canvasRef.current;
    if (!canvas || sharePending || !rendered) return;

    setSharePending(true);
    setShareError(null);
    try {
      const blob = await createPhotoJpegBlob(canvas);
      if (!mountedRef.current) return;
      const result = await createPhotoShare(blob);
      if (!mountedRef.current) return;
      const url = new URL("/share/photo", window.location.origin);
      url.searchParams.set("id", result.shareId);
      setShare({ url: url.toString(), expiresAt: result.expiresAt });
      onShared?.();
    } catch (error) {
      if (mountedRef.current) {
        setShareError(error instanceof PhotoJpegError ? error.message : errorMessage(error));
      }
    } finally {
      if (mountedRef.current) setSharePending(false);
    }
  };

  const { width: outW, height: outH } = BASIC_PHOTO_FRAME.output;

  return (
    <main className="flex min-h-full flex-1 flex-col text-ink">
      {decodeError ? (
        <section
          role="alert"
          className="flex flex-1 flex-col items-center justify-center gap-4 text-center"
        >
          <h1 className="font-display text-[34px] text-ink">사진을 불러오지 못했어요</h1>
          <p className="text-[24px] text-mute">촬영 화면으로 돌아가 다시 시도해 주세요.</p>
          <PillButton size="cta" className="mt-2" onClick={onBack}>
            촬영 화면으로 돌아가기
          </PillButton>
        </section>
      ) : (
        <>
          {/* QR을 만든 뒤에는 화면에서만 숨긴다. 새 QR 만들기가 이 캔버스를 다시 쓴다 */}
          <section
            hidden={Boolean(share)}
            className="flex min-h-0 flex-1 flex-col gap-8 px-12 pt-12 pb-12"
          >
            {/* 제목과 사진을 한 덩어리로 가운데 둔다. 프레임은 남은 높이(cqh)에서 제목 몫을 빼고 맞춘다 */}
            <div
              className="flex min-h-0 flex-1 flex-col items-center justify-center gap-6"
              style={{ containerType: "size" }}
            >
              <div className="flex flex-col items-center gap-2">
                <span className="font-label text-[15px] font-semibold tracking-[.16em] text-navy mirror:text-[20px]">
                  FOUR CUTS
                </span>
                <h1 className="font-display text-[36px] leading-[1.3] text-ink">
                  네 컷이 완성됐어요
                </h1>
              </div>
              <div
                className="relative"
                style={{
                  width: `min(500px, 100cqw, calc((100cqh - 110px) * ${outW / outH}))`,
                }}
              >
                <canvas
                  ref={canvasRef}
                  aria-label="네 장의 사진이 들어간 합성 미리보기"
                  className="block h-auto w-full"
                  style={{ aspectRatio: `${outW}/${outH}` }}
                />
                {!rendered && !renderError && (
                  <p className="absolute inset-0 flex items-center justify-center text-[22px] text-mute">
                    사진을 합치고 있어요
                  </p>
                )}
              </div>
            </div>

            {renderError && (
              <p role="alert" className="text-center text-[22px] text-error">
                미리보기를 만들지 못했어요. 다시 찍어 주세요.
              </p>
            )}
            {shareError && (
              <p role="alert" className="text-center text-[22px] text-error">
                {shareError}
              </p>
            )}

            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-4">
              <PillButton variant="line" size="cta" onClick={onBack}>
                다시 찍기
              </PillButton>
              <PillButton
                size="cta"
                disabled={!rendered}
                busy={sharePending}
                onClick={() => void createShare()}
              >
                {!sharePending && <QrCode className="size-6" strokeWidth={2.2} aria-hidden />}
                {sharePending ? "QR 만드는 중" : "QR로 저장하기"}
              </PillButton>
            </div>
          </section>

          {share && (
            <section className="flex min-h-0 flex-1 flex-col">
              <header className="flex h-28 shrink-0 items-center px-10">
                <button
                  type="button"
                  aria-label="완성 사진으로 돌아가기"
                  onClick={() => setShare(null)}
                  className="flex size-[60px] items-center justify-center rounded-full border border-ink text-ink hover:bg-cream-2"
                >
                  <ChevronLeft className="size-[22px]" strokeWidth={1.9} aria-hidden />
                </button>
              </header>
              <div className="flex flex-1 flex-col items-center justify-center gap-12 px-12 pb-12 text-center">
                {/* QR은 미러 모드에서도 스캔되도록 색을 고정한다(CSS 토큰은 미러에서 반전된다) */}
                <QRCodeSVG
                  value={share.url}
                  size={440}
                  level="M"
                  marginSize={3}
                  fgColor="#0b1430"
                  bgColor="#ffffff"
                  aria-label="네 컷 사진 공유 QR 코드"
                  className="rounded-3xl shadow-float"
                />
                {/* 미러 필름 위에서도 읽히도록 글씨를 크게 두고 흐린 색을 쓰지 않는다 */}
                <div className="flex flex-col items-center gap-5">
                  <span className="font-label text-[20px] font-semibold tracking-[.2em] text-navy">
                    SCAN TO SAVE
                  </span>
                  <p role="status" className="font-display text-[42px] leading-[1.3] text-ink">
                    휴대폰 카메라로 QR을 찍어
                    <br />네 컷 사진을 저장하세요
                  </p>
                  <span className="mt-1 flex items-center gap-2.5 text-[24px] font-semibold text-navy">
                    <Clock className="size-6" strokeWidth={2.2} aria-hidden />
                    {new Date(share.expiresAt).toLocaleTimeString("ko-KR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    까지 스캔할 수 있어요
                  </span>
                </div>
                <PillButton
                  variant="line"
                  size="lg"
                  className="text-[22px]"
                  busy={sharePending}
                  onClick={() => void createShare()}
                >
                  {!sharePending && <RotateCw className="size-6" strokeWidth={2.2} aria-hidden />}새
                  QR 만들기
                </PillButton>
              </div>
              {/* 저장을 마쳤으니 홈 등으로 갈 수 있게 하단 탭을 보인다 */}
              <BottomTabs force />
            </section>
          )}
        </>
      )}
    </main>
  );
}
