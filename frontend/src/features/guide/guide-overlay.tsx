"use client";

import { useEffect, useRef, useState } from "react";

import {
  DEFAULT_PREDICTION,
  FacePredictor,
  faceFitTransform,
  faceWidthRatio,
  MIN_FACE_WIDTH_RATIO,
  halfMirror,
  loadMirrorFit,
  mirrorScreen,
  rescaleAround,
  regionNamesError,
  REGIONS,
  toScreen,
  useCamera,
  useFaceFrame,
  useFaceRender,
  type GuideShape,
  type MeshAnchor,
  type NormalizedRect,
  type ViewTransform,
  type TrackingIssue,
} from "@/features/face";
import { anchorError, loadFaceMesh, MESH_VERSION, type FaceMesh } from "@/features/overlay";
import { observeCanvasSize } from "@/lib/canvas-size";
import { isMirror } from "@/lib/mirror";

import { buildDefaultGuideSet } from "./default-guides";
import { GuideRenderer } from "./renderer";
import { cropTransform } from "./tutorial-crop";
import type { AreaGuideSet, AreaSubStep, GuideArea, GuideSet, GuideStep } from "./types";
import { GuideVisibility, GUIDE_STALE_MS, GUIDE_TURN } from "./visibility";

function anchorsOf(guide: GuideShape): MeshAnchor[] {
  switch (guide.type) {
    case "point":
      return [guide.at];
    case "polyline":
      return guide.path ?? [];
    case "polygon":
      return guide.outline ?? [];
    case "arrow":
      return [guide.from, guide.to];
  }
}

/** 가이드 파일을 불러온다. 메시에서 쓸 수 없는 기준점이 있는 도형은 경고만 남기고 뺀다. */
export async function loadGuideSet(url: string): Promise<GuideSet> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(`가이드 파일을 불러오지 못했습니다: ${url} (${response.status})`);
  const set = (await response.json()) as GuideSet;
  if (set.meshVersion !== MESH_VERSION) {
    throw new Error(
      `가이드 파일의 meshVersion(${set.meshVersion})이 ${MESH_VERSION}이 아닙니다: ${url}`,
    );
  }
  if (!Array.isArray(set.steps)) throw new Error(`가이드 파일에 steps 배열이 없습니다: ${url}`);
  const mesh = await loadFaceMesh();
  const valid = set.steps.filter((step) => {
    const error = !Array.isArray(step.guides)
      ? "guides가 배열이 아닙니다"
      : regionNamesError(step.regions, { allowEmpty: true });
    if (error) console.warn(`${step.stepId} 가이드 단계를 쓸 수 없어 뺍니다: ${error}`);
    return !error;
  });
  const steps = valid.map((step) => ({
    ...step,
    guides: step.guides.filter((guide) => {
      const anchors = anchorsOf(guide) ?? [];
      const error =
        (guide.region ? regionNamesError([guide.region]) : null) ??
        (anchors.length
          ? anchors.map((anchor) => anchorError(anchor, mesh)).find(Boolean)
          : "기준점 없음");
      if (error) console.warn(`${step.stepId} 가이드 도형을 그릴 수 없어 뺍니다: ${error}`);
      return !error;
    }),
  }));
  return { ...set, steps };
}

/** AI가 넘기는 단계별 도포 영역 파일을 불러와 checkGuideArea로 검사한다. */
export async function loadGuideArea(url: string): Promise<GuideArea> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(`가이드 영역 파일을 불러오지 못했습니다: ${url} (${response.status})`);
  return checkGuideArea((await response.json()) as GuideArea, url);
}

/**
 * 단계별 도포 영역을 검사한다. 잘못된 도형은 그 도형만 빼고, 바를 영역(polygon)이 하나도 남지 않은
 * 부위별 묶음은 뺀다. 화살표는 선택 항목이라 영역 없이 화살표만 남은 묶음도 뺀다.
 * 그 때문에 묶음이 하나도 남지 않은 extracted 하위 단계는 failed로 바꾼다.
 * source는 오류 문구에 붙일 출처(파일 경로 등)다.
 */
export async function checkGuideArea(area: GuideArea, source: string): Promise<GuideArea> {
  if (area.meshVersion !== MESH_VERSION) {
    throw new Error(
      `가이드 영역의 meshVersion(${area.meshVersion})이 ${MESH_VERSION}이 아닙니다: ${source}`,
    );
  }
  if (!Array.isArray(area.steps)) throw new Error(`가이드 영역에 steps 배열이 없습니다: ${source}`);
  const mesh = await loadFaceMesh();
  const checkSub = (sub: AreaSubStep): AreaSubStep => {
    if (sub.status !== "extracted") return sub;
    const shapeError = (g: AreaGuideSet["guides"][number]) =>
      g?.type !== "polygon" && g?.type !== "arrow"
        ? "영역 또는 화살표 모양이 아님"
        : g.type === "polygon" && (g.outline?.length ?? 0) < 3
          ? "영역 점이 3개보다 적음"
          : anchorsOf(g)
              .map((a) => anchorError(a, mesh))
              .find(Boolean);
    const guideSets = (sub.guideSets ?? []).flatMap((set) => {
      const error =
        regionNamesError([set.region]) ??
        regionNamesError(set.exclude ?? [], { allowEmpty: true }) ??
        (Array.isArray(set.guides) ? null : "도형 없음");
      if (error) {
        console.warn(`${sub.subStepId} ${set.region} 영역을 쓸 수 없어 뺍니다: ${error}`);
        return [];
      }
      const guides = set.guides.filter((g) => {
        const problem = shapeError(g);
        if (problem) console.warn(`${sub.subStepId} ${set.region} 도형을 빼고 씁니다: ${problem}`);
        return !problem;
      });
      if (!guides.some((g) => g.type === "polygon")) {
        console.warn(`${sub.subStepId} ${set.region} 바를 영역이 없어 뺍니다`);
        return [];
      }
      return [{ ...set, guides }];
    });
    return guideSets.length
      ? { ...sub, guideSets }
      : { ...sub, status: "failed", reasons: ["invalidArea"], guideSets: [] };
  };
  // 하위 단계가 없는 단계는 영역 데이터가 없는 것으로 보고 빼서, 화면이 화장 종류의 기본 가이드를 쓰게 한다
  const steps = area.steps.filter((step) => {
    const ok = Array.isArray(step.subSteps) && step.subSteps.length > 0;
    if (!ok) console.warn(`${step.stepId} 단계에 하위 단계가 없어 영역 데이터에서 뺍니다`);
    return ok;
  });
  return {
    ...area,
    steps: steps.map((step) => ({ ...step, subSteps: step.subSteps.map(checkSub) })),
  };
}

let defaultGuideSet: Promise<GuideSet> | null = null;

/**
 * 외부 가이드 없이 쓰는 9개 부위 기본 가이드. 만드는 데 시간이 걸려 한 번만 만들고 같이 쓴다.
 * 돌려받은 값은 공유 캐시이므로 직접 수정하지 말고, 정렬·가공할 때는 필요한 배열이나 객체를 복사한다.
 */
export function loadDefaultGuideSet(): Promise<GuideSet> {
  defaultGuideSet ??= loadFaceMesh()
    .then((mesh) => buildDefaultGuideSet(mesh, REGIONS))
    .catch((e) => {
      defaultGuideSet = null;
      throw e;
    });
  return defaultGuideSet;
}

/**
 * 지금 단계 부위가 화면 안에 보이는지. 바뀔 때만 다시 그린다.
 * 부위별 표시 기준을 실제 관측에 적용하고 hold 동안에는 직전 판정을 유지한다.
 */
export function useStepInView(step: GuideStep | null, crop: NormalizedRect | null = null): boolean {
  const [inView, setInView] = useState(true);
  const visibility = useRef(new GuideVisibility());
  const stepRef = useRef(step);
  const cropRef = useRef(crop);
  useEffect(() => {
    stepRef.current = step;
    cropRef.current = crop;
  }, [step, crop]);
  useFaceFrame((frame) => {
    const next =
      !stepRef.current ||
      visibility.current.update(stepRef.current, frame, frame?.timestamp, cropRef.current);
    setInView((prev) => (prev === next ? prev : next));
  });
  return inView;
}

export function useGuideTrackingIssue(
  step: GuideStep | null,
  crop: NormalizedRect | null = null,
): TrackingIssue | null {
  const [issue, setIssue] = useState<TrackingIssue | null>("lost");
  const visibility = useRef(new GuideVisibility());
  const stepRef = useRef(step);
  const cropRef = useRef(crop);
  useEffect(() => {
    stepRef.current = step;
    cropRef.current = crop;
  }, [step, crop]);
  useFaceRender((frame, _stats, now) => {
    const current = stepRef.current;
    let next: TrackingIssue | null = null;
    if (
      !frame ||
      frame.trackingState === "lost" ||
      now - (frame.detectedAt ?? frame.timestamp) > GUIDE_STALE_MS
    )
      next = "lost";
    // 미러필름에서도 지금 단계 부위만 본다. 턱이 잘려도 눈 단계면 가이드를 그린다
    else if (current && !visibility.current.update(current, frame, now, cropRef.current)) {
      next = Math.abs(frame.pose.yaw) >= GUIDE_TURN.hidden ? "turned" : "out-of-frame";
    } else if (faceWidthRatio(frame) < MIN_FACE_WIDTH_RATIO) next = "far";
    setIssue((prev) => (prev === next ? prev : next));
  });
  return issue;
}

/** fit일 때 얼굴이 캔버스를 채우는 비율, 확대가 따라가는 빠르기(프레임마다 남은 차이의 몇 배) */
const FACE_FILL = 0.85;
const FIT_FOLLOW = 0.2;
/**
 * 목표 배율이 이 비율보다 적게 달라지면 배율을 그대로 둔다. 하단 안내 높이가 바뀌거나 고개를 조금 움직여도
 * 얼굴 크기가 출렁이지 않게 한다. FACE_FILL 0.85에서 15% 커져도 0.98이라 얼굴이 캔버스를 넘지 않는다.
 */
const FIT_HOLD = 0.15;
/**
 * 점선 굵기·점 크기의 기준인 눈 사이 거리도 같은 방식으로 붙잡는다. 눈 사이 거리는 고개를 조금 돌리거나
 * 홍채 좌표가 떨리기만 해도 프레임마다 바뀌어, 그대로 쓰면 가만히 있어도 점선이 커졌다 작아졌다 한다
 */
const IOD_HOLD = 0.15;

/**
 * CameraProvider 안에서 지금 단계의 가이드를 얼굴 위에 그린다.
 * fit이면 카메라 화면 대신 얼굴을 이 캔버스에 크게 맞춰 그리고, 옅은 얼굴 윤곽을 함께 그린다
 * (영상을 숨기고 가이드만 띄우는 화면용). face로 윤곽만 따로 숨길 수 있다 (화면이 가이드를 숨긴 동안).
 */
export function GuideOverlay({
  step,
  fit = false,
  face = fit,
  crop,
  predictionStrength,
  showStats = false,
}: {
  step: GuideStep | null;
  fit?: boolean;
  face?: boolean;
  crop?: NormalizedRect;
  predictionStrength?: number;
  showStats?: boolean;
}) {
  const { viewTransform } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<GuideRenderer | null>(null);
  const meshRef = useRef<FaceMesh | null>(null);
  const stepRef = useRef(step);
  const faceRef = useRef(face);
  const viewRef = useRef(viewTransform);
  const cropRef = useRef(crop);
  const fitRef = useRef<ViewTransform | null>(null);
  const fitScaleRef = useRef(0);
  const iodRef = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const predictor = useRef(new FacePredictor());
  const predictedStep = useRef(step);
  const lastDraw = useRef(0);
  const perfStart = useRef(0);
  const drawCount = useRef(0);
  const strength = useRef(DEFAULT_PREDICTION.strength);
  const [perf, setPerf] = useState("");

  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("prediction");
    if (value === "off") strength.current = 0;
    else if (value !== null && Number.isFinite(Number(value)))
      strength.current = Math.max(0, Math.min(1, Number(value)));
  }, []);

  useEffect(() => {
    stepRef.current = step;
    faceRef.current = face;
    viewRef.current = viewTransform;
    cropRef.current = crop;
  }, [step, face, viewTransform, crop]);

  useEffect(() => {
    loadFaceMesh()
      .then((mesh) => {
        meshRef.current = mesh;
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new GuideRenderer(canvas);
    rendererRef.current = renderer;
    const unobserve = observeCanvasSize(canvas, (w, h, dpr) => renderer.resize(w, h, dpr));
    return () => {
      unobserve();
      rendererRef.current = null;
    };
  }, []);

  useFaceRender((observed, stats, now) => {
    if (predictedStep.current !== stepRef.current) {
      predictor.current.reset();
      predictedStep.current = stepRef.current;
    }
    predictor.current.sample(observed);
    let frame = predictor.current.predict(now, {
      ...DEFAULT_PREDICTION,
      strength: predictionStrength ?? strength.current,
    });
    const elapsed = lastDraw.current ? Math.min(250, now - lastDraw.current) : 125;
    lastDraw.current = now;
    const canvas = canvasRef.current;
    const crop = cropRef.current;
    let view = viewRef.current;
    const mirror = isMirror();
    // 미러필름 위에서는 비친 얼굴 위치에 그리고 크롭·확대하지 않는다
    if (mirror && frame && canvas) {
      ({ frame, view } = halfMirror(frame, mirrorScreen(canvas), loadMirrorFit()));
    } else if (crop && frame && canvas) {
      view = cropTransform(
        frame.imageSize,
        { width: canvas.clientWidth, height: canvas.clientHeight },
        crop,
      );
    } else if (fit && frame && canvas) {
      const { landmarks } = frame;
      const size = { width: canvas.clientWidth, height: canvas.clientHeight };
      const target = faceFitTransform(
        REGIONS.faceOval.indices.map((i) => landmarks[i]),
        frame.imageSize,
        size,
        FACE_FILL,
      );
      const held = fitScaleRef.current;
      if (!held || Math.abs(target.scale / held - 1) > FIT_HOLD) fitScaleRef.current = target.scale;
      // 얼굴 가운데는 계속 따라가고, 배율만 붙잡아 둔 값을 쓴다
      const goal = rescaleAround(target, fitScaleRef.current, size);
      const prev = fitRef.current;
      const follow = (a: number, b: number) =>
        a + (b - a) * (1 - Math.pow(1 - FIT_FOLLOW, elapsed / 125));
      view = fitRef.current = prev
        ? {
            scale: follow(prev.scale, goal.scale),
            offsetX: follow(prev.offsetX, goal.offsetX),
            offsetY: follow(prev.offsetY, goal.offsetY),
            mirrored: true,
          }
        : goal;
    }
    if (canvas) {
      if (!mirror && crop && frame && view) {
        const x = crop.x0 * frame.imageSize.width * view.scale + view.offsetX;
        const y = crop.y0 * frame.imageSize.height * view.scale + view.offsetY;
        const right =
          canvas.clientWidth - (crop.x1 * frame.imageSize.width * view.scale + view.offsetX);
        const bottom =
          canvas.clientHeight - (crop.y1 * frame.imageSize.height * view.scale + view.offsetY);
        canvas.style.clipPath = `inset(${Math.max(0, y)}px ${Math.max(0, right)}px ${Math.max(0, bottom)}px ${Math.max(0, x)}px)`;
      } else canvas.style.clipPath = "";
    }
    let iod = frame?.iod ?? 0;
    if (frame) {
      const held = iodRef.current;
      if (!held || Math.abs(iod / held - 1) > IOD_HOLD) iodRef.current = iod;
      iod = iodRef.current;
    }
    rendererRef.current?.render({
      frame,
      observedFrame: frame ? observed : null,
      crop: mirror ? undefined : cropRef.current,
      step: stepRef.current,
      mesh: meshRef.current,
      face: faceRef.current,
      nearSideOnly: mirror,
      projection:
        frame && view
          ? { toPx: (p) => toScreen(p, frame.imageSize, view), unit: iod * view.scale }
          : null,
      now,
    });
    drawCount.current++;
    if (!perfStart.current) perfStart.current = now;
    if (showStats && now - perfStart.current >= 500) {
      setPerf(
        [
          `추론 ${stats.fps} FPS · ${stats.backend ?? "-"}`,
          `그리기 ${((drawCount.current * 1000) / (now - perfStart.current)).toFixed(0)} FPS`,
          `관측 경과 ${Math.round(now - (observed?.detectedAt ?? now))}ms · 예측 ${predictionStrength ?? strength.current}`,
          `상태 ${observed?.trackingState ?? "없음"} · yaw ${Math.round(((observed?.pose.yaw ?? 0) * 180) / Math.PI)}°`,
          `표시 부위 ${rendererRef.current?.visibleRegions.join(", ") || "없음"}`,
          `부분 허용 ${observed?.usableRegions?.join(", ") || "없음"}`,
          observed
            ? `화면 안 비율 눈 L ${observed.regionVisibility.leftEye.inFrameRatio.toFixed(2)} · R ${observed.regionVisibility.rightEye.inFrameRatio.toFixed(2)} · 입 ${observed.regionVisibility.lipsOuter.inFrameRatio.toFixed(2)}`
            : "",
        ]
          .filter(Boolean)
          .join("\n"),
      );
      drawCount.current = 0;
      perfStart.current = now;
    }
  });

  return (
    <>
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
      {showStats && (
        <pre className="pointer-events-none absolute top-24 right-2 left-2 rounded bg-black/70 p-2 text-xs whitespace-pre-wrap text-white">
          {perf}
        </pre>
      )}
      {error && (
        <p className="absolute inset-x-0 bottom-4 text-center text-sm text-destructive">{error}</p>
      )}
    </>
  );
}
