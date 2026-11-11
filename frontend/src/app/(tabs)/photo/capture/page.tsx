"use client";

import { Camera, CameraOff, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { CameraError, openCamera } from "@/features/face/camera";
import { BASIC_PHOTO_FRAME, type PhotoSlotId } from "@/features/photo-booth";
import { PhotoEditPreview } from "@/features/photo-booth/photo-edit-preview";

type CameraStatus = "starting" | "ready" | "error";
type CapturedPhotos = Partial<Record<PhotoSlotId, Blob>>;

const SLOT_IDS = BASIC_PHOTO_FRAME.slots.map((slot) => slot.id);

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

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) return Promise.reject(new Error("사진을 만들지 못했어요."));
  context.drawImage(video, 0, 0, canvas.width, canvas.height);

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
  const [mode, setMode] = useState<"capture" | "edit">("capture");

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
        stream = await openCamera(undefined, 1280, 720);
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
      const nextEmpty = SLOT_IDS.find((id) => !next[id]);
      if (nextEmpty) setTargetSlot(nextEmpty);
    } catch (error) {
      setCaptureError(error instanceof Error ? error.message : "사진을 만들지 못했어요.");
    } finally {
      setCapturing(false);
    }
  }, [cameraStatus, capturing, photos, targetSlot]);

  const capturedCount = SLOT_IDS.filter((id) => photos[id]).length;

  useEffect(() => {
    if (capturedCount === 0) return;
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
  }, [capturedCount, router]);

  if (mode === "edit" && capturedCount === SLOT_IDS.length) {
    return (
      <PhotoEditPreview
        photos={photos as Record<PhotoSlotId, Blob>}
        onBack={() => {
          setCameraError(null);
          setCameraStatus("starting");
          setMode("capture");
        }}
      />
    );
  }

  return (
    <main className="flex min-h-0 flex-1 flex-col gap-5 px-6 pt-5 pb-8">
      <header className="flex shrink-0 items-center justify-between">
        <Link href="/photo" className="text-[17px] font-semibold text-navy">
          촬영 안내
        </Link>
        <span className="text-[15px] font-semibold text-mute">
          {capturedCount} / {SLOT_IDS.length}
        </span>
      </header>

      <section className="mx-auto flex w-full max-w-[680px] flex-1 flex-col gap-4">
        <div className="relative flex min-h-[240px] flex-1 items-center justify-center overflow-hidden rounded-3xl bg-ink">
          <video
            ref={videoRef}
            autoPlay
            muted
            playsInline
            onLoadedMetadata={() => setCameraStatus("ready")}
            className="h-full max-h-[min(58dvh,720px)] w-full -scale-x-100 object-contain"
            aria-label="네 컷 사진 카메라 미리보기"
          />
          {cameraStatus === "starting" && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink text-white">
              <Camera className="size-10" aria-hidden />
              <p>카메라를 준비하고 있어요</p>
            </div>
          )}
          {cameraStatus === "error" && (
            <div
              role="alert"
              className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-ink px-8 text-center text-white"
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
                className="flex h-12 items-center gap-2 rounded-full bg-white px-5 font-semibold text-ink"
              >
                <RotateCcw className="size-4" aria-hidden />
                다시 시도
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-4 gap-2" aria-label="촬영할 사진 칸 선택">
          {SLOT_IDS.map((id, index) => {
            const isCaptured = Boolean(photos[id]);
            const isSelected = targetSlot === id;
            return (
              <button
                key={id}
                type="button"
                aria-pressed={isSelected}
                aria-label={`${index + 1}번 사진${isCaptured ? ", 다시 촬영됨" : ", 아직 촬영하지 않음"}`}
                onClick={() => {
                  setTargetSlot(id);
                  setCaptureError(null);
                }}
                className={`flex h-16 flex-col items-center justify-center gap-1 rounded-2xl border ${isSelected ? "border-navy bg-ice text-navy" : "border-line bg-white text-mute"}`}
              >
                <span className="text-[13px]">{index + 1}번</span>
                <span className="text-[12px] font-semibold">
                  {isCaptured ? "촬영 완료" : "촬영 전"}
                </span>
              </button>
            );
          })}
        </div>

        {captureError && (
          <p role="alert" className="text-center text-[15px] text-red-700">
            {captureError}
          </p>
        )}
        {capturedCount === SLOT_IDS.length && (
          <>
            <p role="status" className="text-center text-[15px] text-mute">
              네 장을 모두 촬영했어요. 각 사진을 다시 선택해 바꿀 수 있어요.
            </p>
            <button
              type="button"
              onClick={() => setMode("edit")}
              className="flex h-14 shrink-0 items-center justify-center rounded-full border border-navy bg-white text-[17px] font-bold text-navy"
            >
              사진 편집 및 미리보기
            </button>
          </>
        )}

        <button
          type="button"
          disabled={cameraStatus !== "ready" || capturing}
          onClick={() => void capture()}
          className="flex h-16 shrink-0 items-center justify-center gap-2 rounded-full bg-navy text-[18px] font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Camera className="size-5" aria-hidden />
          {capturing
            ? "사진 저장 중"
            : photos[targetSlot]
              ? `${SLOT_IDS.indexOf(targetSlot) + 1}번 다시 촬영`
              : `${SLOT_IDS.indexOf(targetSlot) + 1}번 촬영`}
        </button>
      </section>
    </main>
  );
}
