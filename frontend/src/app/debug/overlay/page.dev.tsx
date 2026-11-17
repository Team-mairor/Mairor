"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { observeCanvasSize } from "@/lib/canvas-size";
import {
  containTransform,
  REGIONS,
  toScreen,
  type FaceFrame,
  type RegionName,
} from "@/vision/face";
import {
  fitBrowStep,
  findBrows,
  GuideRenderer,
  loadDefaultGuideSet,
  loadGuideArea,
  loadGuideSet,
  resolveSubStep,
  type AreaStatus,
  type GuideArea,
  type GuideSet,
} from "@/vision/guide";
import {
  loadFaceMesh,
  loadLayerSet,
  OverlayRenderer,
  resolveAnchor,
  type FaceMesh,
} from "@/vision/overlay";

const FACES = ["front", "turned-left", "close-up", "far", "blink-hold", "lost"];
const LAYERS = ["sample", "lip-only", "empty", "no-color", "missing-mask"];
const STATUS_LABEL: Record<AreaStatus, string> = {
  extracted: "영상에서 찾은 영역",
  template: "기본 위치",
  notApplicable: "이 단계는 바를 영역이 없어요",
  failed: "영상에서 바를 곳을 찾지 못했어요. 설명을 보고 따라 해 주세요",
};

/**
 * ?step=은 단계 이름(stepId)이나 0부터 센 순서. 이름으로 고르면 가이드 파일을 바꿔도 같은 단계를 본다.
 * 없거나 맞는 단계가 없으면 가이드를 그리지 않는다(-1).
 */
function stepIndex(set: { steps: { stepId: string }[] } | null, value: string | null): number {
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
  const [area, setArea] = useState<GuideArea | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [subKey, setSubKey] = useState<string | null>(null);
  // 단계 이름이나 순서. null이면 가이드를 그리지 않는다.
  const [stepKey, setStepKey] = useState<string | null>(null);
  const step = stepIndex(area ?? guides, stepKey);
  const areaStep = area?.steps[step];
  const bySubId = areaStep?.subSteps.findIndex((s) => s.subStepId === subKey) ?? -1;
  const subIndex =
    bySubId >= 0 ? bySubId : subKey === null ? 0 : /^\d+$/.test(subKey) ? Number(subKey) : -1;
  const sub = areaStep?.subSteps[subIndex] ?? null;
  const guideStep = useMemo(
    () =>
      area
        ? sub
          ? resolveSubStep(sub, guides, areaStep?.makeup)
          : null
        : (guides?.steps[step] ?? null),
    [area, areaStep?.makeup, sub, guides, step],
  );
  const positions =
    area?.steps.flatMap((s, i) =>
      s.subSteps.map((ss) => ({ step: i, stepId: s.stepId, subStepId: ss.subStepId })),
    ) ?? [];
  const position = positions.findIndex(
    (p) => p.stepId === areaStep?.stepId && p.subStepId === sub?.subStepId,
  );
  // 하위 단계를 고르지 않았으면 지금 단계를 기준으로 앞뒤 하위 단계로 간다.
  const prev = position >= 0 ? position - 1 : positions.findLastIndex((p) => p.step < step);
  const next = position >= 0 ? position + 1 : positions.findIndex((p) => p.step >= step);
  const move = (index: number) => {
    const target = positions[index];
    if (!target) return;
    setStepKey(target.stepId);
    setSubKey(target.subStepId);
  };
  const [layersName, setLayersName] = useState(LAYERS[0]);
  // 칠한 얼굴을 등록 사진으로 보고 원래 눈썹을 찾아 눈썹 가이드를 맞춘다
  const [fitBrows, setFitBrows] = useState(false);
  const [mesh, setMesh] = useState<FaceMesh | null>(null);
  const [message, setMessage] = useState("");
  // 상태 문구에 덮이지 않도록 오류는 따로 둔다.
  const [error, setError] = useState("");
  // 가이드 파일 오류는 그리기가 끝날 때 지워지지 않도록 따로 둔다.
  const [guideError, setGuideError] = useState("");
  // 기본 가이드를 못 불러와도 AI 영역은 보이므로, 영역 파일 오류와 따로 알린다.
  const [defaultsError, setDefaultsError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(window.location.search);
    const f = params.get("face");
    const l = params.get("layers");
    // 주소창 값은 브라우저에서만 읽을 수 있다
    /* eslint-disable react-hooks/set-state-in-effect */
    if (f && FACES.includes(f)) setFace(f);
    if (l && LAYERS.includes(l)) setLayersName(l);
    setFitBrows(params.get("brows") === "1");
    setStepKey(params.get("step"));
    setSubKey(params.get("subStep"));
    const areaUrl = params.get("area");
    if (areaUrl && (!l || !LAYERS.includes(l))) setLayersName("empty");
    /* eslint-enable react-hooks/set-state-in-effect */
    loadFaceMesh()
      .then((data) => {
        if (!cancelled) setMesh(data);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    // ?guides=경로 로 가이드 파일을 바꿔 본다 (예: 좌우 확인용 right-only.json)
    const guidesUrl = params.get("guides");
    const load = async () => {
      if (areaUrl) {
        const [areaResult, defaults] = await Promise.allSettled([
          loadGuideArea(areaUrl),
          loadDefaultGuideSet(),
        ]);
        if (cancelled) return;
        if (areaResult.status === "rejected") throw areaResult.reason;
        const data = areaResult.value;
        setArea(data);
        if (defaults.status === "fulfilled") setGuides(defaults.value);
        else setDefaultsError(`기본 가이드를 불러오지 못했습니다: ${String(defaults.reason)}`);
        // AI 영역은 주소에서 고르지 않으면 첫 하위 단계부터 확인한다.
        setStepKey(params.get("step") ?? data.steps[0]?.stepId ?? null);
      } else {
        const data = await (guidesUrl ? loadGuideSet(guidesUrl) : loadDefaultGuideSet());
        if (!cancelled) setGuides(data);
      }
    };
    load()
      .catch((e) => {
        if (!cancelled) setGuideError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
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
      const painted = paintFace(frame);
      let step = guideStep;
      let browNote = "";
      let browLines: { x: number; y: number }[][] = [];
      if (fitBrows && guideStep) {
        const { width: w, height: h } = frame.imageSize;
        const brows = findBrows(painted.getContext("2d")!.getImageData(0, 0, w, h), frame, mesh);
        step = fitBrowStep(guideStep, brows, mesh);
        browNote = ` · 원래 눈썹 ${Object.keys(brows).join("·") || "못 찾음"}`;
        browLines = Object.values(brows).map((outline) =>
          outline.map((a) => resolveAnchor(a, mesh, frame.landmarks)),
        );
      }
      renderer.resize(width, height, dpr);
      renderer.render({
        video: painted,
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
        step,
        mesh,
        projection: {
          toPx: (p) => toScreen(p, frame.imageSize, view),
          unit: frame.iod * view.scale,
        },
        now: 0,
      });
      // 찾은 원래 눈썹 테두리는 가이드와 구분되게 실선으로 긋는다
      const ctx = guideRef.current?.getContext("2d");
      if (ctx && browLines.length) {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.setLineDash([]);
        ctx.strokeStyle = "#22c55e";
        ctx.lineWidth = 1.5;
        for (const line of browLines) {
          ctx.beginPath();
          line.forEach((p, k) => {
            const { x, y } = toScreen(p, frame.imageSize, view);
            if (k === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          });
          ctx.closePath();
          ctx.stroke();
        }
      }
      setError("");
      setMessage(`${frame.trackingState} · 레이어 ${layers.length}개${browNote}`);
    })().catch((e) => {
      if (!cancelled) {
        // 새 선택을 그리지 못했을 때 이전 하위 단계가 현재 영역처럼 남지 않게 한다.
        guide.clear();
        setMessage("");
        setError(String(e));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [face, layersName, mesh, guideStep, size, fitBrows]);

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
          onChange={(e) => {
            setStepKey((area ?? guides)?.steps[Number(e.target.value)]?.stepId ?? null);
            setSubKey(null);
          }}
        >
          <option value={-1}>가이드 없음</option>
          {area
            ? area.steps.map((s, i) => (
                <option key={s.stepId} value={i}>
                  {s.order}. {s.stepId} · {s.makeup}
                </option>
              ))
            : guides?.steps.map((s, i) => (
                <option key={s.stepId} value={i}>
                  가이드 {s.order}. {s.title.split(":")[0]}
                </option>
              ))}
        </select>
        {area && (
          <>
            <select
              aria-label="가이드 하위 단계"
              className="h-8 rounded-lg border bg-background px-2"
              value={sub?.subStepId ?? ""}
              disabled={!areaStep}
              onChange={(e) => setSubKey(e.target.value)}
            >
              <option value="">하위 단계 없음</option>
              {areaStep?.subSteps.map((s) => (
                <option key={s.subStepId} value={s.subStepId}>
                  {s.order}. {s.subStepId} · {s.status}
                </option>
              ))}
            </select>
            <button
              className="rounded-lg border px-3 py-1 disabled:opacity-40"
              disabled={prev < 0}
              onClick={() => move(prev)}
            >
              이전
            </button>
            <button
              className="rounded-lg border px-3 py-1 disabled:opacity-40"
              disabled={next < 0 || next >= positions.length}
              onClick={() => move(next)}
            >
              다음
            </button>
            <span>
              {position >= 0 ? position + 1 : 0} / {positions.length} 하위 단계
            </span>
          </>
        )}
        <label className="flex items-center gap-1">
          <input
            type="checkbox"
            checked={fitBrows}
            onChange={(e) => setFitBrows(e.target.checked)}
          />
          원래 눈썹 맞춤
        </label>
        <span className="text-muted-foreground">{message}</span>
        {error && <span className="text-destructive">{error}</span>}
        {guideError && <span className="text-destructive">{guideError}</span>}
        {defaultsError && <span className="text-destructive">{defaultsError}</span>}
      </div>
      <div aria-live="polite" className="rounded-lg border px-4 py-3 text-sm">
        {!loaded ? (
          "가이드를 불러오는 중"
        ) : guideError ? (
          "가이드를 불러오지 못했어요. 파일 경로와 형식을 확인해 주세요."
        ) : sub ? (
          <>
            <p>
              {areaStep?.stepId} / {sub.subStepId} · {sub.status} · {STATUS_LABEL[sub.status]}
            </p>
            <p>
              기본 가이드 키: {sub.templateId ?? "없음"} · 사유: {sub.reasons.join(", ") || "없음"}
            </p>
            {sub.status === "template" && !guideStep && (
              <p>해당 기본 가이드를 찾지 못해 표시하지 않아요.</p>
            )}
          </>
        ) : (area ?? guides)?.steps.length === 0 ? (
          "이 파일에는 가이드가 없어요"
        ) : area ? (
          "단계와 하위 단계를 선택해 주세요"
        ) : (
          "기본 가이드 또는 파일 가이드를 선택해 주세요"
        )}
      </div>
      <div className="relative">
        <canvas ref={canvasRef} className="aspect-video w-full rounded-lg" />
        <canvas ref={guideRef} className="absolute inset-0 h-full w-full" />
      </div>
    </main>
  );
}
