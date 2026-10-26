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
import { FaceTracker, type TrackerStats } from "./tracker";
import type { FaceFrame, ViewTransform } from "./types";
import { coverTransform } from "./view-transform";

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
    setViewTransform(
      coverTransform(
        { width: video.videoWidth, height: video.videoHeight },
        { width: container.clientWidth, height: container.clientHeight },
        true,
      ),
    );
  }, []);

  // start 도중 stop이 호출되면(페이지 이탈, 개발 모드의 effect 재실행) 진행 중인 start를 버린다.
  const sessionRef = useRef(0);

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
    release();
    setError(null);
    setStatus("idle");
  }, [release]);

  const start = useCallback(async () => {
    const video = videoRef.current;
    if (!video || trackerRef.current) return;

    const session = ++sessionRef.current;
    setStatus("starting");
    setError(null);
    try {
      const stream = await openCamera(undefined, VIDEO_SIZE.width, VIDEO_SIZE.height);
      if (session !== sessionRef.current) {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      video.srcObject = stream;
      await video.play();
      updateTransform();

      const tracker = new FaceTracker(video, (frame, stats) => {
        for (const listener of listeners.current) listener(frame, stats);
      });
      trackerRef.current = tracker;
      await tracker.start();
      if (session !== sessionRef.current) return;
      setStatus("ready");
    } catch (e) {
      if (session !== sessionRef.current) return;
      release();
      setError(e instanceof CameraError ? e : new CameraError("unknown", String(e)));
      setStatus("error");
    }
  }, [release, updateTransform]);

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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 카메라(외부 장치) 연결은 effect에서 시작해야 한다
    if (autoStart) void start();
    return stop;
  }, [autoStart, start, stop]);

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
          playsInline
          muted
        />
        <div className="relative flex flex-1 flex-col">{children}</div>
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
