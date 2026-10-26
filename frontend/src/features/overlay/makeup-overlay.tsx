"use client";

import { useEffect, useRef, useState } from "react";

import { useCamera, useFaceFrame } from "@/features/face";
import { observeCanvasSize } from "@/lib/canvas-size";

import { loadLayerSet, type PreparedLayer } from "./layers";
import { loadFaceMesh, type FaceMesh } from "./mesh";
import { OverlayRenderer } from "./renderer";
import { SkinMask } from "./skin-mask";

// 메시·레이어를 불러오지 못하면 이 간격(ms)마다 다시 시도한다. 부팅 직후 네트워크가 잠깐 끊겨도 살아난다.
const LOAD_RETRY_MS = 5000;
// 피부 분할은 무거워 이 프레임 수마다 한 번 갱신한다.
const SKIN_EVERY = 2;
// 피부 분할이 연달아 이만큼 실패하면 끄고 가림 없이 그린다.
const SKIN_MAX_FAILURES = 3;

/** CameraProvider 안에서 카메라 영상 위에 화장 레이어를 그린다. */
export function MakeupOverlay({
  layersUrl,
  occlusion = true,
}: {
  layersUrl: string | null;
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
  const [error, setError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const skinRef = useRef<SkinMask | null>(null);
  const skinFrame = useRef(0);
  const skinFailures = useRef(0);

  useEffect(() => {
    if (!occlusion) return;
    let cancelled = false;
    let skin: SkinMask | null = null;
    SkinMask.create()
      .then((s) => {
        if (cancelled) return s.dispose();
        skin = s;
        skinRef.current = s;
        skinFailures.current = 0;
      })
      .catch((e) => console.warn("피부 분할을 시작하지 못해 가림을 반영하지 않습니다", e));
    return () => {
      cancelled = true;
      skin?.dispose();
      skinRef.current = null;
    };
  }, [occlusion]);

  useEffect(() => {
    viewRef.current = viewTransform;
    showVideoRef.current = showVideo;
  }, [viewTransform, showVideo]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new OverlayRenderer(canvas);
    rendererRef.current = renderer;
    const unobserve = observeCanvasSize(canvas, (w, h, dpr) => renderer.resize(w, h, dpr));
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

  useFaceFrame((frame) => {
    const skin = skinRef.current;
    const video = videoRef.current;
    // 얼굴을 놓쳤으면 칠할 화장이 없어 분할을 쉰다.
    const tracking = frame && frame.trackingState !== "lost";
    if (skin && video && tracking && skinFrame.current++ % SKIN_EVERY === 0) {
      try {
        skin.update(video);
        skinFailures.current = 0;
      } catch (e) {
        console.error(e);
        if (++skinFailures.current >= SKIN_MAX_FAILURES) {
          console.warn("피부 분할이 계속 실패해 끄고 가림 없이 그립니다");
          skin.dispose();
          skinRef.current = null;
        }
      }
    }
    rendererRef.current?.render({
      video,
      frame,
      view: viewRef.current,
      layers: layersRef.current,
      mesh: meshRef.current,
      drawVideo: showVideoRef.current,
      skinMask: skinRef.current?.canvas ?? null,
      skinVersion: skinRef.current?.version,
    });
  });

  return (
    <>
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
      {error && (
        <p className="absolute inset-x-0 bottom-4 text-center text-sm text-destructive">{error}</p>
      )}
    </>
  );
}
