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

import { isMirror, subscribeMirror } from "@/lib/mirror";
import { cn } from "@/lib/utils";

import { CameraError, openCamera } from "./camera";
import { CameraErrorView } from "./camera-error-view";
import { FaceTracker, type TrackerStats, VideoStalledError } from "./tracker";
import type { FaceFrame, ViewTransform } from "./types";
import { containTransform, visibleRect } from "./view-transform";

export type CameraStatus = "idle" | "starting" | "ready" | "error";

type FrameListener = (frame: FaceFrame | null, stats: TrackerStats) => void;
type RenderListener = (frame: FaceFrame | null, stats: TrackerStats, now: number) => void;

interface CameraContextValue {
  status: CameraStatus;
  error: CameraError | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  /** 화면 좌표 변환. 영상 크기를 알기 전에는 null */
  viewTransform: ViewTransform | null;
  /** 하프미러 앞에서는 영상을 숨기고 가이드만 그린다. */
  showVideo: boolean;
  setShowVideo: (show: boolean) => void;
  /** 카메라 아래쪽을 덮는 패널. 패널 뒤 부위는 화면 밖으로 판정한다 */
  setCoverPanel: (panel: HTMLElement | null) => void;
  start: () => Promise<void>;
  stop: () => void;
  subscribe: (listener: FrameListener) => () => void;
  subscribeRender: (listener: RenderListener) => () => void;
}

const CameraContext = createContext<CameraContextValue | null>(null);

// 전면 센서가 4:3이라 좌우가 덜 잘리고, 1280×720보다 빠르다.
const VIDEO_SIZE = { width: 640, height: 480 };
const EMPTY_STATS: TrackerStats = {
  fps: 0,
  inputScale: 1,
  blink: { left: 0, right: 0 },
  timing: { input: 0, detect: 0, frame: 0, largest: 0, listeners: 0, idle: 0 },
};

// 카메라와 얼굴 추적을 한 번만 시작해 하위 페이지가 함께 쓴다.
export function CameraProvider({
  children,
  autoStart = true,
  errorView = "replace",
}: {
  children: ReactNode;
  autoStart?: boolean;
  /** replace: 오류 화면으로 바꿈(확인 화면용). none: 자식을 그대로 두고 화면이 직접 error를 보여 준다 */
  errorView?: "replace" | "none";
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const trackerRef = useRef<FaceTracker | null>(null);
  // 화면을 떠날 때는 videoRef가 먼저 비워져, 끌 스트림을 따로 들고 있는다.
  const streamRef = useRef<MediaStream | null>(null);
  const listeners = useRef(new Set<FrameListener>());
  const renderListeners = useRef(new Set<RenderListener>());
  const latest = useRef<{ frame: FaceFrame | null; stats: TrackerStats } | null>(null);
  const renderHandle = useRef<number | null>(null);

  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<CameraError | null>(null);
  const [showVideo, setShowVideo] = useState(true);
  const [viewTransform, setViewTransform] = useState<ViewTransform | null>(null);
  const coverPanelRef = useRef<HTMLElement | null>(null);
  const coverObserverRef = useRef<ResizeObserver | null>(null);

  const updateTransform = useCallback(() => {
    const video = videoRef.current;
    const container = containerRef.current;
    if (!video?.videoWidth || !container) return;
    const image = { width: video.videoWidth, height: video.videoHeight };
    const size = { width: container.clientWidth, height: container.clientHeight };
    // 가까이 가도 덜 잘리도록 영상을 자르지 않는다 (위아래는 빈 띠).
    const view = containTransform(image, size, true);
    setViewTransform(view);
    // 화면에 안 보이는 부위(패널 뒤 포함)는 추적기가 화면 밖으로 판정한다.
    // 미러필름 위에서는 어두운 패널도 거울이라 그 뒤 얼굴이 비쳐 보이므로 가리지 않은 것으로 본다
    const panel = isMirror() ? null : coverPanelRef.current;
    const covered = panel
      ? Math.max(0, container.getBoundingClientRect().bottom - panel.getBoundingClientRect().top)
      : 0;
    const visible = { width: size.width, height: Math.max(1, size.height - covered) };
    trackerRef.current?.setOptions({ visibleRect: visibleRect(image, visible, view) });
  }, []);

  const setCoverPanel = useCallback(
    (panel: HTMLElement | null) => {
      coverObserverRef.current?.disconnect();
      coverObserverRef.current = null;
      coverPanelRef.current = panel;
      if (panel) {
        coverObserverRef.current = new ResizeObserver(updateTransform);
        coverObserverRef.current.observe(panel);
      }
      updateTransform();
    },
    [updateTransform],
  );

  // start 도중 stop이 호출되면(페이지 이탈, 개발 모드의 effect 재실행) 진행 중인 start를 버린다.
  const sessionRef = useRef(0);
  // 다시 시도 버튼과 권한 change 이벤트처럼 start가 겹쳐 불려도 카메라는 한 번만 연다.
  const startingRef = useRef<Promise<void> | null>(null);
  // 프레임을 받는 곳이 없어 추적을 쉬는 중. 카메라와 모델은 그대로 둔다
  const pausedRef = useRef(false);

  const release = useCallback(() => {
    latest.current = null;
    pausedRef.current = false;
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
          latest.current = { frame, stats };
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

  // 프레임을 받는 곳이 없으면 추적을 쉬고, 생기면 다시 돌린다. 시작 중이면 끝난 뒤 맞춘다
  const syncTracking = useCallback(() => {
    const tracker = trackerRef.current;
    if (!tracker || startingRef.current) return;
    const wanted = listeners.current.size + renderListeners.current.size > 0;
    if (!wanted && !pausedRef.current) {
      tracker.stop();
      pausedRef.current = true;
    } else if (wanted && pausedRef.current) {
      pausedRef.current = false;
      // 쉬는 동안 화면이 꺼졌다 켜지면 브라우저가 영상을 멈춘 채 둔다
      const video = videoRef.current;
      if (video?.paused)
        video.play().catch((e) => console.warn("카메라 영상을 다시 재생하지 못했습니다", e));
      tracker.reset();
      latest.current = null;
      tracker.start().then(
        // 다시 시작하는 사이 또 쉬게 됐으면 시작한 루프를 멈춘다
        () => {
          if (pausedRef.current) tracker.stop();
        },
        (e) => fail(new CameraError("tracker-failed", e instanceof Error ? e.message : String(e))),
      );
    }
  }, [fail]);

  const start = useCallback(() => {
    if (!startingRef.current && !trackerRef.current) {
      const starting = startSession().finally(() => {
        if (startingRef.current === starting) startingRef.current = null;
        syncTracking();
      });
      startingRef.current = starting;
    }
    return startingRef.current ?? Promise.resolve();
  }, [startSession, syncTracking]);

  const subscribe = useCallback(
    (listener: FrameListener) => {
      listeners.current.add(listener);
      syncTracking();
      return () => {
        listeners.current.delete(listener);
        syncTracking();
      };
    },
    [syncTracking],
  );

  const subscribeRender = useCallback(
    (listener: RenderListener) => {
      renderListeners.current.add(listener);
      syncTracking();
      const draw = (now: number) => {
        renderHandle.current = null;
        if (document.visibilityState === "visible") {
          const { frame, stats } = latest.current ?? { frame: null, stats: EMPTY_STATS };
          for (const callback of renderListeners.current) {
            try {
              callback(frame, stats, now);
            } catch (error) {
              console.error(error);
            }
          }
        }
        if (renderListeners.current.size) renderHandle.current = requestAnimationFrame(draw);
      };
      if (renderHandle.current === null) renderHandle.current = requestAnimationFrame(draw);
      return () => {
        renderListeners.current.delete(listener);
        if (!renderListeners.current.size && renderHandle.current !== null) {
          cancelAnimationFrame(renderHandle.current);
          renderHandle.current = null;
        }
        syncTracking();
      };
    },
    [syncTracking],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(updateTransform);
    observer.observe(container);
    const unsubscribe = subscribeMirror(updateTransform);
    return () => {
      observer.disconnect();
      unsubscribe();
    };
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
      setCoverPanel,
      start,
      stop,
      subscribe,
      subscribeRender,
    }),
    [
      status,
      error,
      viewTransform,
      showVideo,
      setCoverPanel,
      start,
      stop,
      subscribe,
      subscribeRender,
    ],
  );

  return (
    <CameraContext.Provider value={value}>
      <div ref={containerRef} className="relative flex flex-1 flex-col overflow-hidden">
        <video
          ref={videoRef}
          className={cn(
            "absolute inset-0 h-full w-full -scale-x-100 object-contain",
            !showVideo && "invisible",
          )}
          onLoadedMetadata={updateTransform}
          onResize={updateTransform}
          playsInline
          muted
        />
        <div className="relative flex flex-1 flex-col">
          {status === "error" && error && errorView === "replace" ? (
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

/** 이 화면에 있는 동안 카메라 영상을 숨긴다. 카메라와 추적은 그대로 돈다 */
export function useHiddenVideo() {
  const { setShowVideo } = useCamera();
  useEffect(() => {
    setShowVideo(false);
    return () => setShowVideo(true);
  }, [setShowVideo]);
}

/** 그려지면 카메라를 켠다. 이미 켜져 있으면 그대로 쓴다. */
export function StartCamera() {
  const { start } = useCamera();
  useEffect(() => {
    void start();
  }, [start]);
  return null;
}

/** 실제 추론 결과마다 호출된다. 주사율로 그릴 때는 `useFaceRender`를 쓴다. */
export function useFaceFrame(listener: FrameListener) {
  const { subscribe } = useCamera();
  const listenerRef = useRef(listener);

  useEffect(() => {
    listenerRef.current = listener;
  }, [listener]);

  useEffect(() => subscribe((frame, stats) => listenerRef.current(frame, stats)), [subscribe]);
}

/** 최신 실제 관측을 화면 주사율로 전달한다. 예측은 그리는 쪽에서만 적용한다. */
export function useFaceRender(listener: RenderListener) {
  const { subscribeRender } = useCamera();
  const listenerRef = useRef(listener);
  useEffect(() => {
    listenerRef.current = listener;
  }, [listener]);
  useEffect(
    () => subscribeRender((frame, stats, now) => listenerRef.current(frame, stats, now)),
    [subscribeRender],
  );
}
