"use client";

import { Camera, CameraOff, ChevronLeft, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import {
  BASIC_PHOTO_FRAME,
  BEAUTY_CAPTURE_FILTER,
  BEAUTY_PREVIEW_FILTER,
  calculatePhotoCaptureCrop,
  findPhotoFrameOption,
  PhotoBeautyFilterDefs,
  PhotoPreview,
  useAutoWhiteBalance,
  type PhotoFrameOption,
  type PhotoSlot,
  type PhotoSlotId,
} from "@/features/photo-booth";
import { cn } from "@/lib/utils";
import { CameraError, openCamera } from "@/vision/face";

type CameraStatus = "starting" | "ready" | "error";
type CapturedPhotos = Partial<Record<PhotoSlotId, Blob>>;

/** 슬롯 ID는 모든 프레임이 같다 */
const SLOT_IDS = BASIC_PHOTO_FRAME.slots.map((slot) => slot.id);
/** 컷마다 이 시간이 지나면 자동으로 찍는다. 그 전에 셔터를 누르면 바로 찍는다 */
const AUTO_SHOT_SECONDS = 10;

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

function captureJpeg(video: HTMLVideoElement, slot: PhotoSlot): Promise<Blob> {
  if (!video.videoWidth || !video.videoHeight) {
    return Promise.reject(new Error("카메라 영상이 아직 준비되지 않았어요."));
  }

  const crop = calculatePhotoCaptureCrop(
    { width: video.videoWidth, height: video.videoHeight },
    slot,
  );
  const canvas = document.createElement("canvas");
  canvas.width = crop.width;
  canvas.height = crop.height;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("사진을 만들지 못했어요."));
  // 미지원 브라우저는 이 값을 무시해 보정 없이 저장된다
  context.filter = BEAUTY_CAPTURE_FILTER;
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

/** 선택한 프레임으로 얼굴 인식 없이 네 장을 차례로 연속 촬영하고, 샘플 화면에서 고른 컷만 다시 촬영한다. */
function PhotoCapture({ frame }: { frame: PhotoFrameOption }) {
  const photoSlot = frame.template.slots[0];
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

  useAutoWhiteBalance(videoRef, mode === "capture" && cameraStatus === "ready");

  const capture = useCallback(async () => {
    const video = videoRef.current;
    if (cameraStatus !== "ready" || !video || capturing) return;
    setCapturing(true);
    setCaptureError(null);
    try {
      const photo = await captureJpeg(video, photoSlot);
      const next = { ...photos, [targetSlot]: photo };
      setPhotos(next);
      setShared(false);
      const nextEmpty = SLOT_IDS.find((id) => !next[id]);
      if (nextEmpty) setTargetSlot(nextEmpty);
      else setMode("preview");
    } catch (error) {
      setCaptureError(error instanceof Error ? error.message : "사진을 만들지 못했어요.");
    } finally {
      setCapturing(false);
    }
  }, [cameraStatus, capturing, photos, photoSlot, targetSlot]);

  const capturedCount = SLOT_IDS.filter((id) => photos[id]).length;
  // 네 장을 다 찍은 뒤 촬영 화면에 있다면 샘플에서 고른 컷을 다시 찍는 중이다
  const retaking = capturedCount === SLOT_IDS.length;

  const openCapture = (slot: PhotoSlotId) => {
    setCameraError(null);
    setCameraStatus("starting");
    setCaptureError(null);
    setTargetSlot(slot);
    setMode("capture");
  };

  const autoShot = mode === "capture" && cameraStatus === "ready" && !capturing;
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
        frame={frame}
        photos={photos as Record<PhotoSlotId, Blob>}
        onRetake={openCapture}
        onRestart={() => {
          setPhotos({});
          openCapture(SLOT_IDS[0]);
        }}
        onShared={() => setShared(true)}
      />
    );
  }

  const targetIndex = SLOT_IDS.indexOf(targetSlot);
  const guest = frame.guests?.[targetIndex];

  return (
    <main data-photo-booth className="flex min-h-full flex-1 flex-col text-ink">
      <PhotoBeautyFilterDefs />
      <header className="flex h-28 shrink-0 items-center px-10">
        {retaking ? (
          <button
            type="button"
            aria-label="샘플로 돌아가기"
            onClick={() => setMode("preview")}
            className="flex size-[60px] items-center justify-center rounded-full border border-ink text-ink hover:bg-cream-2"
          >
            <ChevronLeft className="size-[22px]" strokeWidth={1.9} aria-hidden />
          </button>
        ) : (
          <Link
            href="/photo/frame"
            aria-label="프레임 다시 고르기"
            className="flex size-[60px] items-center justify-center rounded-full border border-ink text-ink hover:bg-cream-2"
          >
            <ChevronLeft className="size-[22px]" strokeWidth={1.9} aria-hidden />
          </Link>
        )}
      </header>

      <section className="flex min-h-0 flex-1 flex-col gap-8 px-12 pt-4 pb-12">
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <div
            data-dark
            className="relative max-h-full w-full overflow-hidden rounded-3xl bg-black text-white"
            style={{ aspectRatio: `${photoSlot.width}/${photoSlot.height}` }}
          >
            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              onLoadedMetadata={() => setCameraStatus("ready")}
              className="absolute inset-0 h-full w-full -scale-x-100 object-cover"
              style={{ filter: BEAUTY_PREVIEW_FILTER }}
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
            {guest && frame.guestHoleWidth && (
              // 합성 프레임과 같은 이미지·위치라 찍을 때 본 그대로 결과에 들어간다. 너비는 칸 너비 대비 %
              // eslint-disable-next-line @next/next/no-img-element -- 정적 오버레이 이미지
              <img
                key={targetIndex}
                src={guest.src}
                alt={`${targetIndex + 1}번 컷 함께 찍는 사람`}
                width={guest.width}
                height={guest.height}
                className="absolute bottom-0 block h-auto"
                style={{
                  [guest.side]: 0,
                  width: `${(guest.width / frame.guestHoleWidth) * 100}%`,
                }}
              />
            )}
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

        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-6">
          {/* 진행 표시. 컷은 순서대로만 찍으므로 누를 수 없다 */}
          <div
            className="flex gap-2.5"
            role="status"
            aria-label={`${targetIndex + 1}번째 컷 촬영 중`}
          >
            {SLOT_IDS.map((id, index) => (
              <span
                key={id}
                aria-hidden
                className={cn(
                  "flex h-23 w-17 items-end rounded-2xl pb-2 pl-2.5 font-serif text-[28px] leading-none italic mirror:font-label mirror:text-[26px] mirror:font-bold mirror:not-italic",
                  targetSlot === id
                    ? "bg-navy text-white"
                    : photos[id]
                      ? "border-2 border-navy bg-white text-navy"
                      : "border-2 border-line-3 bg-white text-mute",
                )}
              >
                0{index + 1}
              </span>
            ))}
          </div>
          <button
            type="button"
            aria-label={`${targetIndex + 1}번 컷 ${retaking ? "다시 " : ""}촬영`}
            disabled={cameraStatus !== "ready" || capturing}
            onClick={() => void capture()}
            className="group flex size-33 rounded-full border-[5px] border-navy p-2 transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
          >
            <span className="flex-1 rounded-full bg-navy transition-transform group-active:scale-95" />
          </button>
          <div className="flex justify-end">
            {retaking && (
              <PillButton variant="line" size="cta" onClick={() => setMode("preview")}>
                취소
              </PillButton>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}

function PhotoCaptureGate() {
  const router = useRouter();
  const frame = findPhotoFrameOption(useSearchParams().get("frame"));

  // 프레임을 고르지 않고 들어오면 선택 화면으로 보낸다
  useEffect(() => {
    if (!frame) router.replace("/photo/frame");
  }, [frame, router]);

  return frame ? <PhotoCapture key={frame.id} frame={frame} /> : null;
}

export default function PhotoCapturePage() {
  return (
    <Suspense>
      <PhotoCaptureGate />
    </Suspense>
  );
}
