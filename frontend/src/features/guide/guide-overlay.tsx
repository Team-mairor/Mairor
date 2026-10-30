"use client";

import { useEffect, useRef, useState } from "react";

import {
  MIN_IN_FRAME_RATIO,
  RECOVER_IN_FRAME_MARGIN,
  regionNamesError,
  REGIONS,
  toScreen,
  useCamera,
  useFaceFrame,
  type GuideShape,
  type MeshAnchor,
} from "@/features/face";
import { anchorError, loadFaceMesh, MESH_VERSION, type FaceMesh } from "@/features/overlay";
import { observeCanvasSize } from "@/lib/canvas-size";

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

/** CameraProvider 안에서 지금 단계의 가이드를 얼굴 위에 그린다. */
export function GuideOverlay({ step }: { step: GuideStep | null }) {
  const { viewTransform } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<GuideRenderer | null>(null);
  const meshRef = useRef<FaceMesh | null>(null);
  const stepRef = useRef(step);
  const viewRef = useRef(viewTransform);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    stepRef.current = step;
    viewRef.current = viewTransform;
  }, [step, viewTransform]);

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

  useFaceFrame((frame) => {
    const view = viewRef.current;
    rendererRef.current?.render({
      frame,
      step: stepRef.current,
      mesh: meshRef.current,
      // 지금은 카메라 화면 기준. 하프미러는 거울에 비친 상 위치로 바꿔 넘긴다.
      projection:
        frame && view
          ? { toPx: (p) => toScreen(p, frame.imageSize, view), unit: frame.iod * view.scale }
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
