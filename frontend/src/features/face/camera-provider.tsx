"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import { cn } from "@/lib/utils";

import { CameraError, openCamera } from "./camera";
import { CameraErrorView } from "./camera-error-view";
import { FaceTracker, type TrackerStats, VideoStalledError } from "./tracker";
import type { FaceFrame, ViewTransform } from "./types";
import { coverTransform, visibleRect } from "./view-transform";

export type CameraStatus = "idle" | "starting" | "ready" | "error";

type FrameListener = (frame: FaceFrame | null, stats: TrackerStats) => void;

interface CameraContextValue {
  status: CameraStatus;
  error: CameraError | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  /** 화면 좌표 변환. 영상 크기를 알기 전에는 null */
  viewTransform: ViewTransform | null;
  /** 하프미러 앞에서는 영상을 숨기고 가이드만 그린다. */
  showVideo: boolean;
  setShowVideo: (show: boolean) => void;
  start: () => Promise<void>;
  stop: () => void;
  subscribe: (listener: FrameListener) => () => void;
}

const CameraContext = createContext<CameraContextValue | null>(null);

const VIDEO_SIZE = { width: 1280, height: 720 };

// 카메라와 얼굴 추적을 한 번만 시작해 하위 페이지가 함께 쓴다.
export function CameraProvider({
  children,
  autoStart = true,
}: {
  children: ReactNode;
  autoStart?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const trackerRef = useRef<FaceTracker | null>(null);
  // 화면을 떠날 때는 videoRef가 먼저 비워져, 끌 스트림을 따로 들고 있는다.
  const streamRef = useRef<MediaStream | null>(null);
  const listeners = useRef(new Set<FrameListener>());

  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<CameraError | null>(null);
  const [showVideo, setShowVideo] = useState(true);
  const [viewTransform, setViewTransform] = useState<ViewTransform | null>(null);

  const updateTransform = useCallback(() => {
    const video = videoRef.current;
    const container = containerRef.current;
    if (!video?.videoWidth || !container) return;
    const image = { width: video.videoWidth, height: video.videoHeight };
    const size = { width: container.clientWidth, height: container.clientHeight };
    const view = coverTransform(image, size, true);
    setViewTransform(view);
    // 화면 비율이 달라 잘린 부위는 추적기가 화면 밖으로 판정하게 한다.
    trackerRef.current?.setOptions({ visibleRect: visibleRect(image, size, view) });
  }, []);

  // start 도중 stop이 호출되면(페이지 이탈, 개발 모드의 effect 재실행) 진행 중인 start를 버린다.
  const sessionRef = useRef(0);
  // 다시 시도 버튼과 권한 change 이벤트처럼 start가 겹쳐 불려도 카메라는 한 번만 연다.
  const startingRef = useRef<Promise<void> | null>(null);

  const release = useCallback(() => {
    trackerRef.current?.dispose();
    trackerRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    const video = videoRef.current;
    if (video) video.srcObject = null;
  }, []);

  const stop = useCallback(() => {
    sessionRef.current += 1;
    startingRef.current = null;
    release();
    setError(null);
    setStatus("idle");
  }, [release]);

  const fail = useCallback(
    (e: unknown) => {
      // 모델을 불러오는 중에 실패해도 다시 시도하면 바로 새로 시작하도록 진행 중인 시작을 버린다.
      startingRef.current = null;
      release();
      setError(e instanceof CameraError ? e : new CameraError("unknown", String(e)));
      setStatus("error");
    },
    [release],
  );

  const startSession = useCallback(async () => {
    const video = videoRef.current;
    if (!video) return;

    const session = ++sessionRef.current;
    setStatus("starting");
    setError(null);
    try {
      const stream = await openCamera(undefined, VIDEO_SIZE.width, VIDEO_SIZE.height);
      if (session !== sessionRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      // 시작한 뒤에 생긴 오류. 진행 중인 세션을 끝내고 오류 화면으로 바꾼다.
      const abort = (error: CameraError) => {
        if (session !== sessionRef.current) return;
        sessionRef.current += 1;
        fail(error);
      };
      // 케이블이 빠지거나 권한이 회수되면 트랙이 끝난다.
      stream.getVideoTracks()[0]?.addEventListener("ended", () => {
        abort(new CameraError("disconnected", "카메라 연결이 끊어졌습니다"));
      });
      streamRef.current = stream;
      video.srcObject = stream;
      await video.play();
      // 영상을 켜는 동안 stop되었으면 이 세션의 카메라만 끈다. 새 세션의 영상은 건드리지 않는다.
      if (session !== sessionRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      updateTransform();

      const tracker = new FaceTracker(
        video,
        (frame, stats) => {
          for (const listener of listeners.current) {
            try {
              listener(frame, stats);
            } catch (e) {
              console.error(e);
            }
          }
        },
        {},
        (e) =>
          abort(
            e instanceof VideoStalledError
              ? new CameraError("disconnected", e.message)
              : new CameraError("tracker-failed", String(e)),
          ),
      );
      trackerRef.current = tracker;
      // 보이는 영역을 새 추적기에도 알려 준다.
      updateTransform();
      try {
        await tracker.start();
      } catch (e) {
        throw new CameraError("tracker-failed", e instanceof Error ? e.message : String(e));
      }
      if (session !== sessionRef.current) return;
      setStatus("ready");
    } catch (e) {
      if (session !== sessionRef.current) return;
      fail(e);
    }
  }, [fail, updateTransform]);

  const start = useCallback(() => {
    if (!startingRef.current && !trackerRef.current) {
      const starting = startSession().finally(() => {
        if (startingRef.current === starting) startingRef.current = null;
      });
      startingRef.current = starting;
    }
    return startingRef.current ?? Promise.resolve();
  }, [startSession]);

  const subscribe = useCallback((listener: FrameListener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(updateTransform);
    observer.observe(container);
    return () => observer.disconnect();
  }, [updateTransform]);

  useEffect(() => {
    if (autoStart) void start();
    return stop;
  }, [autoStart, start, stop]);

  // 권한 거부 후 사용자가 브라우저 설정에서 허용하면 바로 다시 시작한다.
  const permissionDenied = status === "error" && error?.kind === "permission-denied";
  useEffect(() => {
    if (!permissionDenied || !navigator.permissions) return;
    let permission: PermissionStatus | null = null;
    let cancelled = false;
    const onChange = () => {
      if (permission?.state === "granted") void start();
    };
    navigator.permissions
      .query({ name: "camera" as PermissionName })
      .then((p) => {
        if (cancelled) return;
        permission = p;
        p.addEventListener("change", onChange);
      })
      // camera 권한 조회를 지원하지 않는 브라우저는 다시 시도 버튼으로만 복구한다.
      .catch(() => {});
    return () => {
      cancelled = true;
      permission?.removeEventListener("change", onChange);
    };
  }, [permissionDenied, start]);

  const value = useMemo(
    () => ({
      status,
      error,
      videoRef,
      viewTransform,
      showVideo,
      setShowVideo,
      start,
      stop,
      subscribe,
    }),
    [status, error, viewTransform, showVideo, start, stop, subscribe],
  );

  return (
    <CameraContext.Provider value={value}>
      <div ref={containerRef} className="relative flex flex-1 flex-col overflow-hidden">
        <video
          ref={videoRef}
          className={cn(
            "absolute inset-0 h-full w-full -scale-x-100 object-cover",
            !showVideo && "invisible",
          )}
          onLoadedMetadata={updateTransform}
          onResize={updateTransform}
          playsInline
          muted
        />
        <div className="relative flex flex-1 flex-col">
          {status === "error" && error ? (
            <CameraErrorView error={error} onRetry={() => void start()} />
          ) : (
            children
          )}
        </div>
      </div>
    </CameraContext.Provider>
  );
}

export function useCamera() {
  const context = useContext(CameraContext);
  if (!context) throw new Error("useCamera는 CameraProvider 안에서만 쓸 수 있습니다");
  return context;
}

/** 프레임마다 호출된다. 화면 그리기처럼 리렌더 없이 처리할 일에 쓴다. */
export function useFaceFrame(listener: FrameListener) {
  const { subscribe } = useCamera();
  const listenerRef = useRef(listener);

  useEffect(() => {
    listenerRef.current = listener;
  }, [listener]);

  useEffect(() => subscribe((frame, stats) => listenerRef.current(frame, stats)), [subscribe]);
}
