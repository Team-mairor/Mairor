"use client";

import { ArrowRight, Camera, CameraOff, ChevronLeft, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { CameraError, openCamera } from "@/features/face";
import {
  BASIC_PHOTO_FRAME,
  calculatePhotoCaptureCrop,
  PhotoPreview,
  type PhotoSlotId,
} from "@/features/photo-booth";
import { cn } from "@/lib/utils";

type CameraStatus = "starting" | "ready" | "error";
type CapturedPhotos = Partial<Record<PhotoSlotId, Blob>>;

const SLOT_IDS = BASIC_PHOTO_FRAME.slots.map((slot) => slot.id);
const PHOTO_SLOT = BASIC_PHOTO_FRAME.slots[0];
/** 아직 안 찍은 컷은 이 시간이 지나면 자동으로 찍는다. 그 전에 셔터를 누르면 바로 찍는다 */
const AUTO_SHOT_SECONDS = 7;
/**
 * 촬영 화면에 겹쳐 보이는 함께 찍는 사람. 합성 프레임과 같은 이미지·위치라 찍을 때 본 그대로 결과에 들어간다.
 * width는 칸 너비(구멍 822px) 대비 %, 모두 칸 아래쪽에 붙는다.
 */
const CAPTURE_GUESTS = [
  { side: "left", width: (454 / 822) * 100 },
  { side: "left", width: (489 / 822) * 100 },
  { side: "right", width: (478 / 822) * 100 },
  { side: "right", width: (639 / 822) * 100 },
] as const;

function cameraErrorText(error: CameraError) {
  switch (error.kind) {
    case "insecure":
      return "카메라는 HTTPS 주소에서만 사용할 수 있어요.";
    case "unsupported":
      return "이 브라우저에서는 카메라를 사용할 수 없어요.";
    case "permission-denied":
      return "브라우저 설정에서 카메라 접근을 허용해 주세요.";
    case "blocked":
      return "브라우저나 기기 정책에서 카메라 사용을 차단했어요.";
    case "not-found":
      return "연결된 카메라를 찾을 수 없어요.";
    case "in-use":
      return "다른 앱에서 카메라를 사용 중인지 확인해 주세요.";
    case "disconnected":
      return "카메라 연결이 끊겼어요. 연결을 확인한 뒤 다시 시도해 주세요.";
    default:
      return "카메라를 시작하지 못했어요. 잠시 후 다시 시도해 주세요.";
  }
}

function captureJpeg(video: HTMLVideoElement): Promise<Blob> {
  if (!video.videoWidth || !video.videoHeight) {
    return Promise.reject(new Error("카메라 영상이 아직 준비되지 않았어요."));
  }

  const crop = calculatePhotoCaptureCrop(
    { width: video.videoWidth, height: video.videoHeight },
    PHOTO_SLOT,
  );
  const canvas = document.createElement("canvas");
  canvas.width = crop.width;
  canvas.height = crop.height;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("사진을 만들지 못했어요."));
  context.drawImage(
    video,
    crop.x,
    crop.y,
    crop.width,
    crop.height,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("사진을 만들지 못했어요."))),
      "image/jpeg",
      0.92,
    );
  });
}

/** 얼굴 인식 없이 네 장을 촬영하고, 선택한 칸의 사진을 다시 촬영한다. */
export default function PhotoCapturePage() {
  const router = useRouter();
  const videoRef = useRef<HTMLVideoElement>(null);
  const restoringHistoryRef = useRef(false);
  const [cameraStatus, setCameraStatus] = useState<CameraStatus>("starting");
  const [cameraError, setCameraError] = useState<CameraError | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [photos, setPhotos] = useState<CapturedPhotos>({});
  const [targetSlot, setTargetSlot] = useState<PhotoSlotId>(SLOT_IDS[0]);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const [capturing, setCapturing] = useState(false);
  const [mode, setMode] = useState<"capture" | "preview">("capture");
  // QR 공유를 만들면 사진이 휴대폰으로 넘어갔으므로 나가기 경고를 끈다
  const [shared, setShared] = useState(false);

  useEffect(() => {
    if (mode !== "capture") return;
    let cancelled = false;
    let stream: MediaStream | null = null;
    let video: HTMLVideoElement | null = videoRef.current;
    const onTrackEnded = () => {
      if (cancelled) return;
      stream?.getTracks().forEach((track) => track.stop());
      if (video?.srcObject === stream) video.srcObject = null;
      setCameraError(new CameraError("disconnected", "카메라 연결이 끊겼습니다"));
      setCameraStatus("error");
    };

    const startCamera = async () => {
      try {
        stream = await openCamera(undefined, 1920, 1080);
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        stream.getVideoTracks()[0]?.addEventListener("ended", onTrackEnded);
        video = videoRef.current;
        if (!video) throw new Error("카메라 화면을 준비하지 못했어요.");
        video.srcObject = stream;
        await video.play();
        if (!cancelled && video.videoWidth > 0) setCameraStatus("ready");
      } catch (error) {
        if (cancelled) return;
        stream?.getTracks().forEach((track) => track.stop());
        if (video?.srcObject === stream) video.srcObject = null;
        setCameraError(
          error instanceof CameraError
            ? error
            : new CameraError("unknown", error instanceof Error ? error.message : String(error)),
        );
        setCameraStatus("error");
      }
    };

    void startCamera();
    return () => {
      cancelled = true;
      stream?.getVideoTracks()[0]?.removeEventListener("ended", onTrackEnded);
      stream?.getTracks().forEach((track) => track.stop());
      if (video?.srcObject === stream) video.srcObject = null;
    };
  }, [mode, retryKey]);

  const capture = useCallback(async () => {
    const video = videoRef.current;
    if (cameraStatus !== "ready" || !video || capturing) return;
    setCapturing(true);
    setCaptureError(null);
    try {
      const photo = await captureJpeg(video);
      const next = { ...photos, [targetSlot]: photo };
      setPhotos(next);
      setShared(false);
      const nextEmpty = SLOT_IDS.find((id) => !next[id]);
      if (nextEmpty) setTargetSlot(nextEmpty);
    } catch (error) {
      setCaptureError(error instanceof Error ? error.message : "사진을 만들지 못했어요.");
    } finally {
      setCapturing(false);
    }
  }, [cameraStatus, capturing, photos, targetSlot]);

  const capturedCount = SLOT_IDS.filter((id) => photos[id]).length;

  // 다시 찍기(이미 찍은 컷)는 셔터로만 찍는다. 자동 촬영은 빈 컷에서만 센다
  const autoShot =
    mode === "capture" && cameraStatus === "ready" && !capturing && !photos[targetSlot];
  const [countdown, setCountdown] = useState<number | null>(null);
  const captureRef = useRef(capture);
  useEffect(() => {
    captureRef.current = capture;
  }, [capture]);
  useEffect(() => {
    if (!autoShot) return;
    let left = AUTO_SHOT_SECONDS;
    let timer = 0;
    const tick = () => {
      if (left === 0) {
        void captureRef.current();
        return;
      }
      setCountdown(left);
      left -= 1;
      timer = window.setTimeout(tick, 1000);
    };
    timer = window.setTimeout(tick, 0);
    return () => {
      window.clearTimeout(timer);
      setCountdown(null);
    };
  }, [autoShot, targetSlot]);

  useEffect(() => {
    if (capturedCount === 0 || shared) return;
    const warning = `촬영한 사진 ${capturedCount}장이 이 화면을 나가면 사라져요. 나갈까요?`;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const onDocumentClick = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        !(event.target instanceof Element)
      ) {
        return;
      }
      const anchor = event.target.closest<HTMLAnchorElement>("a[href]");
      if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) return;

      const destination = new URL(anchor.href, window.location.href);
      if (
        destination.origin !== window.location.origin ||
        (destination.pathname === window.location.pathname &&
          destination.search === window.location.search)
      ) {
        return;
      }

      event.preventDefault();
      if (window.confirm(warning)) {
        router.push(`${destination.pathname}${destination.search}${destination.hash}`);
      }
    };
    const onPopState = () => {
      if (restoringHistoryRef.current) {
        restoringHistoryRef.current = false;
        return;
      }
      if (!window.confirm(warning)) {
        restoringHistoryRef.current = true;
        window.history.forward();
      }
    };

    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("popstate", onPopState);
    document.addEventListener("click", onDocumentClick, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("popstate", onPopState);
      document.removeEventListener("click", onDocumentClick, true);
    };
  }, [capturedCount, shared, router]);

  if (mode === "preview" && capturedCount === SLOT_IDS.length) {
    return (
      <PhotoPreview
        photos={photos as Record<PhotoSlotId, Blob>}
        onBack={() => {
          setCameraError(null);
          setCameraStatus("starting");
          setMode("capture");
        }}
        onShared={() => setShared(true)}
      />
    );
  }

  const targetIndex = SLOT_IDS.indexOf(targetSlot);
  const guest = CAPTURE_GUESTS[targetIndex];
  const allCaptured = capturedCount === SLOT_IDS.length;

  return (
    <main data-photo-booth className="flex min-h-full flex-1 flex-col text-ink">
      <header className="flex h-28 shrink-0 items-center px-10">
        <Link
          href="/photo"
          aria-label="뒤로"
          className="flex size-[60px] items-center justify-center rounded-full border border-ink text-ink hover:bg-cream-2"
        >
          <ChevronLeft className="size-[22px]" strokeWidth={1.9} aria-hidden />
        </Link>
      </header>

      <section className="flex min-h-0 flex-1 flex-col gap-8 px-12 pt-4 pb-12">
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <div
            data-dark
            className="relative max-h-full w-full overflow-hidden rounded-3xl bg-black text-white"
            style={{ aspectRatio: `${PHOTO_SLOT.width}/${PHOTO_SLOT.height}` }}
          >
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              onLoadedMetadata={() => setCameraStatus("ready")}
              className="absolute inset-0 h-full w-full -scale-x-100 object-cover"
              aria-label="네 컷 사진 카메라 미리보기"
            />
            {[1, 2].map((line) => (
              <span
                key={`v${line}`}
                aria-hidden
                className="absolute inset-y-0 w-0.5 bg-white/20"
                style={{ left: `${(line * 100) / 3}%` }}
              />
            ))}
            {[1, 2].map((line) => (
              <span
                key={`h${line}`}
                aria-hidden
                className="absolute inset-x-0 h-0.5 bg-white/20"
                style={{ top: `${(line * 100) / 3}%` }}
              />
            ))}
            {/* eslint-disable-next-line @next/next/no-img-element -- 정적 오버레이 이미지 */}
            <img
              src={`/images/photo/guest-${targetIndex + 1}.png`}
              alt={`${targetIndex + 1}번 컷 함께 찍는 사람`}
              className="absolute bottom-0 block h-auto"
              style={{ [guest.side]: 0, width: `${guest.width}%` }}
            />
            <span className="absolute top-7 left-7 rounded-full bg-night/55 px-5 py-2.5 font-label text-[18px] font-semibold tracking-[.16em] text-white backdrop-blur-sm mirror:text-[24px]">
              CUT 0{targetIndex + 1}
            </span>
            <span className="absolute top-7 right-7 rounded-full bg-white px-6 py-3 font-display text-[24px] whitespace-nowrap text-ink">
              {capturing
                ? "사진 저장 중"
                : countdown
                  ? `${countdown}초 뒤 자동 촬영`
                  : "포즈를 잡아 주세요"}
            </span>
            {countdown !== null && countdown <= 3 && (
              <span
                key={countdown}
                aria-hidden
                className="absolute inset-0 flex animate-fade items-center justify-center font-display text-[180px] text-white drop-shadow-lg"
              >
                {countdown}
              </span>
            )}
            {cameraStatus === "starting" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black text-[24px]">
                <Camera className="size-10" aria-hidden />
                <p>카메라를 준비하고 있어요</p>
              </div>
            )}
            {cameraStatus === "error" && (
              <div
                role="alert"
                className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-black px-8 text-center text-[24px]"
              >
                <CameraOff className="size-10" aria-hidden />
                <p>{cameraError ? cameraErrorText(cameraError) : "카메라를 시작하지 못했어요."}</p>
                <button
                  type="button"
                  onClick={() => {
                    setCameraError(null);
                    setCameraStatus("starting");
                    setRetryKey((key) => key + 1);
                  }}
                  className="flex h-14 items-center gap-2 rounded-full bg-ice px-6 font-semibold text-ink"
                >
                  <RotateCcw className="size-5" aria-hidden />
                  다시 시도
                </button>
              </div>
            )}
          </div>
        </div>

        {captureError && (
          <p role="alert" className="text-center text-[22px] text-error">
            {captureError}
          </p>
        )}
        {/* 네 장을 다 찍으면 셔터를 흐리게 두고 완성 버튼으로 눈이 가게 한다. 셔터는 고른 컷 다시 찍기용으로 남긴다 */}
        {allCaptured && !captureError && (
          <p role="status" className="text-center text-[24px] font-bold text-navy">
            네 장을 다 찍었어요! 완성을 눌러 주세요
          </p>
        )}

        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-6">
          <div className="flex gap-2.5" aria-label="촬영할 컷 선택">
            {SLOT_IDS.map((id, index) => {
              const isCaptured = Boolean(photos[id]);
              const isSelected = targetSlot === id;
              return (
                <button
                  key={id}
                  type="button"
                  aria-pressed={isSelected}
                  aria-label={`${index + 1}번 컷${isCaptured ? " 다시 찍기" : ""}`}
                  onClick={() => {
                    setTargetSlot(id);
                    setCaptureError(null);
                  }}
                  className={cn(
                    "flex h-23 w-17 items-end rounded-2xl pb-2 pl-2.5 font-serif text-[28px] leading-none italic mirror:font-label mirror:text-[26px] mirror:font-bold mirror:not-italic",
                    isSelected
                      ? "bg-navy text-white"
                      : isCaptured
                        ? "border-2 border-navy bg-white text-navy"
                        : "border-2 border-line-3 bg-white text-mute",
                  )}
                >
                  0{index + 1}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            aria-label={
              photos[targetSlot]
                ? `${targetIndex + 1}번 컷 다시 촬영`
                : `${targetIndex + 1}번 컷 촬영`
            }
            disabled={cameraStatus !== "ready" || capturing}
            onClick={() => void capture()}
            className={cn(
              "group flex size-33 rounded-full border-[5px] border-navy p-2 transition-opacity disabled:cursor-not-allowed disabled:opacity-40",
              allCaptured && "opacity-40 hover:opacity-70",
            )}
          >
            <span className="flex-1 rounded-full bg-navy transition-transform group-active:scale-95" />
          </button>
          <div className="flex justify-end">
            <div className="relative">
              {allCaptured && (
                <span
                  aria-hidden
                  className="absolute -inset-2 animate-pulse rounded-full border-4 border-navy"
                />
              )}
              <PillButton
                size="cta"
                disabled={!allCaptured}
                className="relative"
                onClick={() => setMode("preview")}
              >
                완성
                <ArrowRight className="size-6" strokeWidth={2.4} aria-hidden />
              </PillButton>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
