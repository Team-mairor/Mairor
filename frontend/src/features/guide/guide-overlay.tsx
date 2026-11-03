"use client";

import { useEffect, useRef, useState } from "react";

import {
  faceFitTransform,
  halfMirror,
  loadMirrorFit,
  MIN_IN_FRAME_RATIO,
  mirrorScreen,
  rescaleAround,
  RECOVER_IN_FRAME_MARGIN,
  regionNamesError,
  REGIONS,
  toScreen,
  useCamera,
  useFaceFrame,
  type GuideShape,
  type MeshAnchor,
  type ViewTransform,
} from "@/features/face";
import { anchorError, loadFaceMesh, MESH_VERSION, type FaceMesh } from "@/features/overlay";
import { observeCanvasSize } from "@/lib/canvas-size";
import { isMirror } from "@/lib/mirror";

import { buildDefaultGuideSet } from "./default-guides";
import { GuideRenderer, isStepVisible } from "./renderer";
import type { AreaSubStep, GuideArea, GuideSet, GuideStep } from "./types";

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
      const error = anchors.length
        ? anchors.map((anchor) => anchorError(anchor, mesh)).find(Boolean)
        : "기준점 없음";
      if (error) console.warn(`${step.stepId} 가이드 도형을 그릴 수 없어 뺍니다: ${error}`);
      return !error;
    }),
  }));
  return { ...set, steps };
}

/**
 * AI가 넘기는 단계별 도포 영역을 불러온다. 쓸 수 없는 부위별 묶음은 경고만 남기고 빼고,
 * 그 때문에 영역이 하나도 남지 않은 extracted 하위 단계는 failed로 바꾼다.
 */
export async function loadGuideArea(url: string): Promise<GuideArea> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(`가이드 영역 파일을 불러오지 못했습니다: ${url} (${response.status})`);
  const area = (await response.json()) as GuideArea;
  if (area.meshVersion !== MESH_VERSION) {
    throw new Error(
      `가이드 영역 파일의 meshVersion(${area.meshVersion})이 ${MESH_VERSION}이 아닙니다: ${url}`,
    );
  }
  if (!Array.isArray(area.steps))
    throw new Error(`가이드 영역 파일에 steps 배열이 없습니다: ${url}`);
  const mesh = await loadFaceMesh();
  const checkSub = (sub: AreaSubStep): AreaSubStep => {
    if (sub.status !== "extracted") return sub;
    const guideSets = (sub.guideSets ?? []).filter((set) => {
      const error =
        regionNamesError([set.region]) ??
        regionNamesError(set.exclude ?? [], { allowEmpty: true }) ??
        (!Array.isArray(set.guides) || set.guides.length === 0
          ? "도형 없음"
          : set.guides.some((g) => g.type !== "polygon" || (g.outline?.length ?? 0) < 3)
            ? "테두리 점이 3개보다 적음"
            : set.guides
                .flatMap(anchorsOf)
                .map((a) => anchorError(a, mesh))
                .find(Boolean));
      if (error) console.warn(`${sub.subStepId} ${set.region} 영역을 쓸 수 없어 뺍니다: ${error}`);
      return !error;
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
 * 추적이 불안정할 때는 추적 판정이 따로 안내하므로 직전 값을 유지한다.
 */
export function useStepInView(step: GuideStep | null): boolean {
  const [inView, setInView] = useState(true);
  const stepRef = useRef(step);
  useEffect(() => {
    stepRef.current = step;
  }, [step]);
  useFaceFrame((frame) => {
    if (frame?.trackingState !== "tracking") return;
    // 추적기처럼 한번 숨긴 뒤에는 조금 더 들어와야 다시 보이게 해 경계에서 깜빡이지 않게 한다.
    setInView((prev) => {
      const limit = MIN_IN_FRAME_RATIO + (prev ? 0 : RECOVER_IN_FRAME_MARGIN);
      const next = !stepRef.current || isStepVisible(stepRef.current, frame, limit);
      return prev === next ? prev : next;
    });
  });
  return inView;
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
}: {
  step: GuideStep | null;
  fit?: boolean;
  face?: boolean;
}) {
  const { viewTransform } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<GuideRenderer | null>(null);
  const meshRef = useRef<FaceMesh | null>(null);
  const stepRef = useRef(step);
  const faceRef = useRef(face);
  const viewRef = useRef(viewTransform);
  const fitRef = useRef<ViewTransform | null>(null);
  const fitScaleRef = useRef(0);
  const iodRef = useRef(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    stepRef.current = step;
    faceRef.current = face;
    viewRef.current = viewTransform;
  }, [step, face, viewTransform]);

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

  useFaceFrame((camFrame) => {
    const canvas = canvasRef.current;
    let frame = camFrame;
    let view = viewRef.current;
    // 미러필름 위에서는 거울에 비친 얼굴 위치에 그린다. 비친 얼굴이 곧 실제 크기라 확대(fit)하지 않는다
    if (isMirror() && frame && canvas) {
      ({ frame, view } = halfMirror(frame, mirrorScreen(canvas), loadMirrorFit()));
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
      const follow = (a: number, b: number) => a + (b - a) * FIT_FOLLOW;
      view = fitRef.current = prev
        ? {
            scale: follow(prev.scale, goal.scale),
            offsetX: follow(prev.offsetX, goal.offsetX),
            offsetY: follow(prev.offsetY, goal.offsetY),
            mirrored: true,
          }
        : goal;
    }
    let iod = frame?.iod ?? 0;
    if (frame) {
      const held = iodRef.current;
      if (!held || Math.abs(iod / held - 1) > IOD_HOLD) iodRef.current = iod;
      iod = iodRef.current;
    }
    rendererRef.current?.render({
      frame,
      step: stepRef.current,
      mesh: meshRef.current,
      face: faceRef.current,
      projection:
        frame && view
          ? { toPx: (p) => toScreen(p, frame.imageSize, view), unit: iod * view.scale }
          : null,
      now: performance.now(),
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
