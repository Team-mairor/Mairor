"use client";

import { useEffect, useRef, useState } from "react";

import {
  containTransform,
  REGIONS,
  toScreen,
  type FaceFrame,
  type RegionName,
} from "@/features/face";
import { GuideRenderer, loadDefaultGuideSet, loadGuideSet, type GuideSet } from "@/features/guide";
import { loadFaceMesh, loadLayerSet, OverlayRenderer, type FaceMesh } from "@/features/overlay";
import { observeCanvasSize } from "@/lib/canvas-size";

const FACES = ["front", "turned-left", "close-up", "far", "blink-hold", "lost"];
const LAYERS = ["sample", "lip-only", "empty", "no-color", "missing-mask"];

/**
 * ?step=은 단계 이름(stepId)이나 0부터 센 순서. 이름으로 고르면 가이드 파일을 바꿔도 같은 단계를 본다.
 * 없거나 맞는 단계가 없으면 가이드를 그리지 않는다(-1).
 */
function stepIndex(set: GuideSet | null, value: string | null): number {
  if (!set || value === null) return -1;
  const byId = set.steps.findIndex((s) => s.stepId === value);
  if (byId >= 0) return byId;
  return /^\d+$/.test(value) && Number(value) < set.steps.length ? Number(value) : -1;
}

async function loadFace(name: string): Promise<FaceFrame> {
  const url = `/fixtures/faces/${name}.json`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`얼굴 파일을 불러오지 못했습니다: ${url} (${response.status})`);
  return (await response.json()) as FaceFrame;
}

// 카메라 대신 픽스처 얼굴을 단색으로 칠해 바탕으로 쓴다.
function paintFace(frame: FaceFrame): HTMLCanvasElement {
  const { width, height } = frame.imageSize;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#3a3a3a";
  ctx.fillRect(0, 0, width, height);

  const fill = (name: RegionName, color: string) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    REGIONS[name].indices.forEach((i, k) => {
      const p = frame.landmarks[i];
      const x = p.x * width;
      const y = p.y * height;
      if (k === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fill();
  };
  fill("faceOval", "#d9ab8f");
  fill("lipsOuter", "#c98b7f");
  fill("lipsInner", "#5a2a2a");
  fill("rightEye", "#f2f2f2");
  fill("leftEye", "#f2f2f2");
  fill("rightBrow", "#4a3328");
  fill("leftBrow", "#4a3328");
  return canvas;
}

export default function DebugOverlayPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const guideRef = useRef<HTMLCanvasElement>(null);
  // 선택을 바꿀 때마다 만들면 WebGL 컨텍스트가 쌓여, 렌더러는 한 번만 만든다.
  const rendererRef = useRef<OverlayRenderer | null>(null);
  // 가이드도 한 번만 만들어야 직전 판정이 남아, 깜빡임(hold) 동안 유지되는지 확인할 수 있다.
  const guideRendererRef = useRef<GuideRenderer | null>(null);
  const [size, setSize] = useState<{ width: number; height: number; dpr: number } | null>(null);
  const [face, setFace] = useState(FACES[0]);
  const [guides, setGuides] = useState<GuideSet | null>(null);
  // 단계 이름이나 순서. null이면 가이드를 그리지 않는다.
  const [stepKey, setStepKey] = useState<string | null>(null);
  const step = stepIndex(guides, stepKey);
  const [layersName, setLayersName] = useState(LAYERS[0]);
  const [mesh, setMesh] = useState<FaceMesh | null>(null);
  const [message, setMessage] = useState("");
  // 상태 문구에 덮이지 않도록 오류는 따로 둔다.
  const [error, setError] = useState("");
  // 가이드 파일 오류는 그리기가 끝날 때 지워지지 않도록 따로 둔다.
  const [guideError, setGuideError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const f = params.get("face");
    const l = params.get("layers");
    // 주소창 값은 브라우저에서만 읽을 수 있다
    /* eslint-disable react-hooks/set-state-in-effect */
    if (f && FACES.includes(f)) setFace(f);
    if (l && LAYERS.includes(l)) setLayersName(l);
    setStepKey(params.get("step"));
    /* eslint-enable react-hooks/set-state-in-effect */
    loadFaceMesh()
      .then(setMesh)
      .catch((e) => setError(String(e)));
    // ?guides=경로 로 가이드 파일을 바꿔 본다 (예: 좌우 확인용 right-only.json)
    const guidesUrl = params.get("guides");
    (guidesUrl ? loadGuideSet(guidesUrl) : loadDefaultGuideSet())
      .then(setGuides)
      .catch((e) => setGuideError(String(e)));
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const guideCanvas = guideRef.current;
    if (!canvas || !guideCanvas) return;
    const renderer = new OverlayRenderer(canvas);
    rendererRef.current = renderer;
    guideRendererRef.current = new GuideRenderer(guideCanvas);
    // 창 크기나 화면 배율이 바뀌면 다시 그린다.
    const unobserve = observeCanvasSize(canvas, (width, height, dpr) =>
      setSize({ width, height, dpr }),
    );
    return () => {
      unobserve();
      renderer.dispose();
      rendererRef.current = null;
      guideRendererRef.current = null;
    };
  }, []);

  useEffect(() => {
    const renderer = rendererRef.current;
    const guide = guideRendererRef.current;
    if (!renderer || !guide || !mesh || !size) return;
    let cancelled = false;

    (async () => {
      const frame = await loadFace(face);
      const layers = await loadLayerSet(`/fixtures/layers/${layersName}.json`, mesh);
      if (cancelled) return;

      const { width, height, dpr } = size;
      renderer.resize(width, height, dpr);
      renderer.render({
        video: paintFace(frame),
        frame,
        view: containTransform(frame.imageSize, { width, height }, true),
        layers,
        mesh,
        drawVideo: true,
      });
      const view = containTransform(frame.imageSize, { width, height }, true);
      guide.resize(width, height, dpr);
      guide.render({
        frame,
        step: guides?.steps[step] ?? null,
        mesh,
        projection: {
          toPx: (p) => toScreen(p, frame.imageSize, view),
          unit: frame.iod * view.scale,
        },
        now: 0,
      });
      setError("");
      setMessage(`${frame.trackingState} · 레이어 ${layers.length}개`);
    })().catch((e) => {
      if (!cancelled) setError(String(e));
    });

    return () => {
      cancelled = true;
    };
  }, [face, layersName, mesh, guides, step, size]);

  return (
    <main className="flex flex-1 flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <select
          aria-label="얼굴 픽스처"
          className="h-8 rounded-lg border bg-background px-2"
          value={face}
          onChange={(e) => setFace(e.target.value)}
        >
          {FACES.map((f) => (
            <option key={f}>{f}</option>
          ))}
        </select>
        <select
          aria-label="레이어 픽스처"
          className="h-8 rounded-lg border bg-background px-2"
          value={layersName}
          onChange={(e) => setLayersName(e.target.value)}
        >
          {LAYERS.map((l) => (
            <option key={l}>{l}</option>
          ))}
        </select>
        <select
          aria-label="가이드 단계"
          className="h-8 rounded-lg border bg-background px-2"
          value={step}
          onChange={(e) => setStepKey(guides?.steps[Number(e.target.value)]?.stepId ?? null)}
        >
          <option value={-1}>가이드 없음</option>
          {guides?.steps.map((s, i) => (
            <option key={s.stepId} value={i}>
              가이드 {s.order}. {s.title.split(":")[0]}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground">{message}</span>
        {error && <span className="text-destructive">{error}</span>}
        {guideError && <span className="text-destructive">{guideError}</span>}
      </div>
      <div className="relative">
        <canvas ref={canvasRef} className="aspect-video w-full rounded-lg" />
        <canvas ref={guideRef} className="absolute inset-0 h-full w-full" />
      </div>
    </main>
  );
}
