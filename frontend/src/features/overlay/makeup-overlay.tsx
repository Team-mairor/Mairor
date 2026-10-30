"use client";

import { useEffect, useRef, useState } from "react";

import { formatTiming, landmarkerInfo, useCamera, useFaceFrame } from "@/features/face";
import { observeCanvasSize } from "@/lib/canvas-size";

import { loadLayerSet, type PreparedLayer } from "./layers";
import { loadFaceMesh, type FaceMesh } from "./mesh";
import { OverlayRenderer } from "./renderer";
import { SkinMask } from "./skin-mask";

// 메시·레이어를 불러오지 못하면 이 간격(ms)마다 다시 시도한다. 부팅 직후 네트워크가 잠깐 끊겨도 살아난다.
const LOAD_RETRY_MS = 5000;
// 피부 분할은 무거워 이 프레임 수마다 한 번 갱신한다.
const SKIN_EVERY = 2;
// 화장 캔버스는 CSS 픽셀의 절반 해상도로 그린다. 화장 그리기의 GPU 작업이 끝나야 얼굴 검출 결과를 읽을 수
// 있어, 그릴 픽셀이 곧 검출 지연이 된다. 하프미러 위에서는 흐린 화장의 해상도 차이가 거의 보이지 않는다.
const OVERLAY_DPR = 0.5;
// 피부 분할이 연달아 이만큼 실패하면 끄고 가림 없이 그린다.
const SKIN_MAX_FAILURES = 3;
// 피부 분할 한 번이 이 시간(ms)보다 오래 걸리는 일이 연달아 생기면 저사양 기기로 보고 끈다.
// 분할은 화면을 멈추고 돌아, 느린 기기에서는 추적까지 함께 끊긴다.
const SKIN_SLOW_MS = 150;
const SKIN_MAX_SLOW = 2;

// 처리 시간은 프레임마다 흔들려 이동평균으로 보여 준다. 첫 값은 그대로 써서 처음에 낮게 보이지 않게 한다.
const average = (prev: number | null, value: number) =>
  prev === null ? value : prev * 0.9 + value * 0.1;

interface Perf {
  fps: number;
  /** 추적 구간별 시간 (formatTiming) */
  timing: string;
  renderMs: number;
  /** 화장 종류별 그리기 시간 */
  layerMs: string;
  /** null: 분할 꺼짐, "loading": 모델 불러오는 중, "pending": 아직 결과 없음 */
  skinMs: number | null | "loading" | "pending";
  inputScale: number;
  video: string;
  layers: number;
}

/** CameraProvider 안에서 카메라 영상 위에 화장 레이어를 그린다. */
export function MakeupOverlay({
  layersUrl,
  hidden = false,
  enabled = true,
  showStats = false,
  occlusion = true,
}: {
  layersUrl: string | null;
  /** true면 레이어는 그대로 두고 화장만 그리지 않는다. 다시 보일 때 레이어를 새로 불러오지 않는다 */
  hidden?: boolean;
  /** false면 그리지 않는다 (추적만 할 때와 성능 비교용) */
  enabled?: boolean;
  /** FPS·처리 시간 표시 */
  showStats?: boolean;
  /** 앞머리·손 등이 가린 곳에 칠하지 않기 */
  occlusion?: boolean;
}) {
  const { videoRef, viewTransform, showVideo } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<OverlayRenderer | null>(null);
  const meshRef = useRef<FaceMesh | null>(null);
  const layersRef = useRef<PreparedLayer[]>([]);
  const viewRef = useRef(viewTransform);
  const showVideoRef = useRef(showVideo);
  const hiddenRef = useRef(hidden);
  const [error, setError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [perf, setPerf] = useState<Perf | null>(null);
  const renderMs = useRef<number | null>(null);
  const skinMs = useRef<number | null>(null);
  // 분할 모델을 불러오는 중인지. 통계에서 꺼짐과 구분해 보여 준다.
  const skinLoading = useRef(false);
  const lastPerfUpdate = useRef(0);
  const skinRef = useRef<SkinMask | null>(null);
  const skinFrame = useRef(0);
  const skinFailures = useRef(0);
  const skinSlow = useRef(0);
  const skinRuns = useRef(0);

  useEffect(() => {
    if (!enabled || !occlusion) return;
    let cancelled = false;
    let skin: SkinMask | null = null;
    skinLoading.current = true;
    SkinMask.create()
      .then((s) => {
        if (cancelled) return s.dispose();
        skin = s;
        skinRef.current = s;
        skinMs.current = null;
        skinFailures.current = 0;
        skinSlow.current = 0;
        skinRuns.current = 0;
      })
      .catch((e) => console.warn("피부 분할을 시작하지 못해 가림을 반영하지 않습니다", e))
      .finally(() => {
        if (!cancelled) skinLoading.current = false;
      });
    return () => {
      cancelled = true;
      skinLoading.current = false;
      skin?.dispose();
      skinRef.current = null;
    };
  }, [enabled, occlusion]);

  useEffect(() => {
    viewRef.current = viewTransform;
    showVideoRef.current = showVideo;
    hiddenRef.current = hidden;
  }, [viewTransform, showVideo, hidden]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new OverlayRenderer(canvas);
    rendererRef.current = renderer;
    const unobserve = observeCanvasSize(canvas, (w, h, dpr) =>
      renderer.resize(w, h, Math.min(dpr, OVERLAY_DPR)),
    );
    return () => {
      unobserve();
      renderer.dispose();
      rendererRef.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    layersRef.current = [];
    loadFaceMesh()
      .then(async (mesh) => {
        if (cancelled) return;
        // 이전 주소에서 남은 오류 문구를 지운다.
        setError(null);
        meshRef.current = mesh;
        if (!layersUrl) return;
        const layers = await loadLayerSet(layersUrl, mesh);
        if (cancelled) return;
        layersRef.current = layers;
        if (layers.length === 0) setError("그릴 수 있는 화장 레이어가 없어요");
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
        retry = setTimeout(() => setLoadAttempt((n) => n + 1), LOAD_RETRY_MS);
      });
    return () => {
      cancelled = true;
      clearTimeout(retry);
    };
  }, [layersUrl, loadAttempt]);

  useFaceFrame((frame, stats) => {
    const now = performance.now();
    const skin = skinRef.current;
    const video = videoRef.current;
    // 얼굴을 놓쳤거나 화장을 숨겼으면 칠할 곳이 없어 분할을 쉰다.
    const tracking = frame && frame.trackingState !== "lost" && !hiddenRef.current;
    if (enabled && skin && video && tracking && skinFrame.current++ % SKIN_EVERY === 0) {
      let stopReason: string | null = null;
      try {
        skin.update(video);
        skinFailures.current = 0;
        // 첫 호출은 모델 초기화가 섞여 느리게 나오므로 통계와 느림 판정에서 뺀다.
        if (skinRuns.current++ > 0) {
          skinMs.current = average(skinMs.current, skin.lastMs);
          skinSlow.current = skin.lastMs > SKIN_SLOW_MS ? skinSlow.current + 1 : 0;
        }
        if (skinSlow.current >= SKIN_MAX_SLOW) {
          stopReason = `피부 분할이 너무 느려(${Math.round(skin.lastMs)}ms) 끄고 가림 없이 그립니다`;
        }
      } catch (e) {
        console.error(e);
        if (++skinFailures.current >= SKIN_MAX_FAILURES) {
          stopReason = "피부 분할이 계속 실패해 끄고 가림 없이 그립니다";
        }
      }
      if (stopReason) {
        console.warn(stopReason);
        skin.dispose();
        skinRef.current = null;
      }
    }
    if (enabled) {
      // 피부 분할 시간이 섞이지 않도록 그리기만 잰다.
      const start = performance.now();
      rendererRef.current?.render({
        video,
        frame,
        view: viewRef.current,
        layers: hiddenRef.current ? [] : layersRef.current,
        mesh: meshRef.current,
        drawVideo: showVideoRef.current,
        skinMask: skinRef.current?.canvas ?? null,
        skinVersion: skinRef.current?.version,
      });
      renderMs.current = average(renderMs.current, performance.now() - start);
    }

    if (!showStats || now - lastPerfUpdate.current < 250) return;
    lastPerfUpdate.current = now;
    setPerf({
      fps: stats.fps,
      timing: formatTiming(stats.timing),
      renderMs: renderMs.current ?? 0,
      layerMs: Object.entries(rendererRef.current?.layerMs ?? {})
        .map(([k, v]) => `${k} ${v.toFixed(1)}`)
        .join(" · "),
      skinMs: skinRef.current
        ? (skinMs.current ?? "pending")
        : skinLoading.current
          ? "loading"
          : null,
      inputScale: stats.inputScale,
      video: video ? `${video.videoWidth}×${video.videoHeight}` : "-",
      layers: enabled ? layersRef.current.length : 0,
    });
  });

  useEffect(() => {
    if (!enabled)
      rendererRef.current?.render({
        video: null,
        frame: null,
        view: null,
        layers: [],
        mesh: null,
        drawVideo: false,
      });
  }, [enabled]);

  return (
    <>
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
      {showStats && perf && (
        <pre className="absolute top-2 left-2 rounded bg-black/60 px-2 py-1 text-xs text-white">
          {[
            `FPS ${perf.fps}`,
            `추적 ms ${perf.timing}`,
            `그리기 ${perf.renderMs.toFixed(1)}ms`,
            ...(perf.layerMs ? [`  ${perf.layerMs}`] : []),
            `피부 분할 ${
              perf.skinMs === null
                ? "꺼짐"
                : perf.skinMs === "loading"
                  ? "불러오는 중"
                  : perf.skinMs === "pending"
                    ? "준비 중"
                    : `${perf.skinMs.toFixed(1)}ms (${SKIN_EVERY}프레임마다)`
            }`,
            `추론 ${landmarkerInfo.delegate ?? "-"} · ${landmarkerInfo.gpu ?? "WebGL2 없음"}`,
            `입력 배율 ${perf.inputScale.toFixed(2)}`,
            `영상 ${perf.video}`,
            `레이어 ${perf.layers}${enabled ? "" : " (끔)"}`,
          ].join("\n")}
        </pre>
      )}
      {error && (
        <p className="absolute inset-x-0 bottom-4 text-center text-sm text-destructive">{error}</p>
      )}
    </>
  );
}
