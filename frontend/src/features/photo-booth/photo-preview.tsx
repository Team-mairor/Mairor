"use client";

import { Camera, ChevronLeft, Clock, QrCode, RotateCw } from "lucide-react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";

import { BottomTabs } from "@/components/bottom-tabs";
import { PillButton } from "@/components/ui/pill-button";
import { errorMessage } from "@/lib/api";

import { createPhotoJpegBlob, PhotoJpegError } from "./export-jpeg";
import { BASIC_PHOTO_FRAME, type PhotoSlotId } from "./frame";
import type { PhotoFrameOption } from "./frame-options";
import { renderPhotoFrame, type FramePhotos } from "./render";
import { createPhotoShare } from "./share-api";
import { drawPhotoStamp, formatStampDate, loadStampFonts } from "./stamp";

type CapturedPhotos = Record<PhotoSlotId, Blob>;

const SLOT_IDS = BASIC_PHOTO_FRAME.slots.map((slot) => slot.id);
/** 촬영 화면은 거울처럼 좌우 반전해 보여 주므로, 결과도 본 모습 그대로 좌우 반전해 합성한다. */
const MIRRORED = { mirrored: true } as const;

/** 네 장을 프레임에 합성해 보여 주고, 마음에 안 드는 컷을 골라 다시 찍거나 QR 공유로 저장한다. 위치·확대 조정 없이 촬영 그대로 쓴다. */
export function PhotoPreview({
  frame,
  photos,
  onRetake,
  onRestart,
  onShared,
}: {
  /** 선택한 프레임 */
  frame: PhotoFrameOption;
  photos: CapturedPhotos;
  /** 고른 컷만 다시 찍으러 갈 때 */
  onRetake: (slot: PhotoSlotId) => void;
  /** 사진을 읽지 못했을 때 처음부터 다시 찍는다 */
  onRestart: () => void;
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
  const [thumbUrls, setThumbUrls] = useState<Record<PhotoSlotId, string> | null>(null);
  const [shotDate] = useState(() => formatStampDate(new Date()));
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
    let thumbs: string[] = [];

    const decodePhotos = async () => {
      try {
        // 이미지가 있는 프레임은 일반 모드에서 검은 프레임, 미러필름 모드에서 밝은(#f4f9ff) 프레임을 쓴다. 칸 좌표는 같다
        const overlaySrc = document.documentElement.classList.contains("mirror")
          ? (frame.mirrorOverlaySrc ?? frame.template.overlaySrc)
          : frame.template.overlaySrc;
        const [frameImage, decoded] = await Promise.all([
          overlaySrc
            ? fetch(overlaySrc)
                .then((response) => {
                  if (!response.ok) throw new Error("프레임 이미지를 불러오지 못했어요.");
                  return response.blob();
                })
                .then((blob) => createImageBitmap(blob))
            : Promise.resolve(null),
          Promise.all(
            SLOT_IDS.map(async (id) => [id, await createImageBitmap(photos[id])] as const),
          ),
        ]);
        bitmaps = [...(frameImage ? [frameImage] : []), ...decoded.map(([, bitmap]) => bitmap)];
        if (cancelled) {
          bitmaps.forEach((bitmap) => bitmap.close());
          return;
        }
        const bitmapBySlot = new Map(decoded);
        thumbs = SLOT_IDS.map((id) => URL.createObjectURL(photos[id]));
        setThumbUrls(
          Object.fromEntries(SLOT_IDS.map((id, i) => [id, thumbs[i]])) as Record<
            PhotoSlotId,
            string
          >,
        );
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
      thumbs.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [photos, frame]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !images) return;
    let cancelled = false;
    const raf = window.requestAnimationFrame(() => {
      try {
        renderPhotoFrame(canvas, frame.template, images, overlay ?? undefined);
      } catch {
        setRenderError(true);
        return;
      }
      const stamp = frame.stamp;
      if (!stamp) {
        setRendered(true);
        return;
      }
      // 서체를 불러온 뒤 우측 하단에 촬영 날짜와 mairor 글씨를 덧그린다
      void loadStampFonts().then((fonts) => {
        if (cancelled) return;
        const mirrored = document.documentElement.classList.contains("mirror");
        try {
          drawPhotoStamp(canvas, frame.template, {
            date: shotDate,
            color: (mirrored && stamp.mirrorColor) || stamp.color,
            mairor: stamp.mairor,
            scale: stamp.scale,
            fonts,
          });
          setRendered(true);
        } catch {
          setRenderError(true);
        }
      });
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(raf);
    };
  }, [images, overlay, frame, shotDate]);

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

  const { width: outW, height: outH } = frame.template.output;

  return (
    <main className="flex min-h-full flex-1 flex-col text-ink">
      {decodeError ? (
        <section
          role="alert"
          className="flex flex-1 flex-col items-center justify-center gap-4 text-center"
        >
          <h1 className="font-display text-[34px] text-ink">사진을 불러오지 못했어요</h1>
          <p className="text-[24px] text-mute">처음부터 다시 찍어 주세요.</p>
          <PillButton size="cta" className="mt-2" onClick={onRestart}>
            처음부터 다시 찍기
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
                  className="block h-auto w-full shadow-frame"
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

            <div className="flex flex-col items-center gap-4">
              <p className="text-[22px] font-semibold text-navy">다시 찍고 싶은 컷을 눌러 주세요</p>
              <div className="flex gap-4">
                {SLOT_IDS.map((id, index) => (
                  <button
                    key={id}
                    type="button"
                    aria-label={`${index + 1}번 컷 다시 찍기`}
                    onClick={() => onRetake(id)}
                    className="relative h-[132px] w-[99px] overflow-hidden rounded-2xl border-2 border-navy bg-white"
                  >
                    {thumbUrls && (
                      // eslint-disable-next-line @next/next/no-img-element -- 촬영한 사진의 임시 주소
                      <img
                        src={thumbUrls[id]}
                        alt=""
                        className="size-full -scale-x-100 object-cover"
                      />
                    )}
                    <span className="absolute bottom-1.5 left-2 rounded-full bg-night/55 px-2 py-0.5 font-label text-[14px] font-semibold text-white backdrop-blur-sm">
                      0{index + 1}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-4">
              {/* 저장하지 않은 사진이 있으면 촬영 화면이 나가기 전에 한 번 물어본다 */}
              <PillButton asChild variant="line" size="cta" className="px-6">
                <Link href="/photo/frame">
                  <Camera className="size-6" strokeWidth={2.2} aria-hidden />
                  새로 찍기
                </Link>
              </PillButton>
              <PillButton
                size="cta"
                className="flex-1"
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
