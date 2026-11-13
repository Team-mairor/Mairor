"use client";

import { useEffect, useRef, useState, type PointerEvent } from "react";

import { useCamera, type NormalizedRect } from "@/features/face";

import {
  TABLET_WIDTH,
  layoutHeight,
  PC_FRAME_QUERY,
  tutorialAreaHeight,
  TUTORIAL_BOTTOM,
  TUTORIAL_TOP,
  tabletPreviewScale,
  tutorialVideoRatio,
  centeredTutorialCrop,
  resizeTutorialCrop,
} from "./tutorial-crop";
import { CropView, useTutorialCrop } from "./tutorial-viewport";
import type { GuideStep } from "./types";

const FULL = { x0: 0, y0: 0, x1: 1, y1: 1 };
const clamp = (n: number, max: number) => Math.max(0, Math.min(max, n));

export function TutorialCropEditor({
  step,
  predictionStrength,
  showStats,
}: {
  step: GuideStep | null;
  predictionStrength?: number;
  showStats?: boolean;
}) {
  const { crop: saved, save } = useTutorialCrop();
  const { videoRef, status } = useCamera();
  const [rect, setRect] = useState<NormalizedRect>(saved ?? { x0: 0.1, y0: 0.3, x1: 0.9, y1: 0.7 });
  const [imageRatio, setImageRatio] = useState<number | null>(null);
  const [screen, setScreen] = useState({ width: 1, height: 1 });
  const [pcFrame, setPcFrame] = useState(false);
  const [preview, setPreview] = useState(false);
  const [message, setMessage] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const initializedRatio = useRef<number | null>(null);
  const previousSaved = useRef(saved);
  const drag = useRef<{ x: number; y: number; rect: NormalizedRect; resize: boolean } | null>(null);
  useEffect(() => {
    const update = () => {
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      const pc = matchMedia(PC_FRAME_QUERY).matches;
      setScreen(viewport);
      setPcFrame(pc);
      const v = videoRef.current;
      const ratio = tutorialVideoRatio(v);
      setImageRatio(ratio);
      const savedChanged = previousSaved.current !== saved;
      previousSaved.current = saved;
      if (ratio !== null && (initializedRatio.current !== ratio || savedChanged)) {
        setRect(
          (initializedRatio.current === null || savedChanged) && saved
            ? saved
            : centeredTutorialCrop(ratio, tutorialAreaHeight(layoutHeight(viewport, pc))),
        );
        initializedRatio.current = ratio;
        drag.current = null;
      }
    };
    const video = videoRef.current;
    update();
    window.addEventListener("resize", update);
    video?.addEventListener("loadedmetadata", update);
    video?.addEventListener("resize", update);
    video?.addEventListener("emptied", update);
    return () => {
      window.removeEventListener("resize", update);
      video?.removeEventListener("loadedmetadata", update);
      video?.removeEventListener("resize", update);
      video?.removeEventListener("emptied", update);
    };
  }, [videoRef, saved, status]);
  const cameraReady = status === "ready" && imageRatio !== null;
  // 이 기기에서 실제 tutorial이 쓰는 높이로 영역 비율을 잡는다
  const appHeight = layoutHeight(screen, pcFrame);
  const areaHeight = tutorialAreaHeight(appHeight);
  const previewScale = tabletPreviewScale(screen, appHeight);
  const center = () => {
    if (imageRatio === null) return;
    setRect(centeredTutorialCrop(imageRatio, areaHeight));
    setMessage("");
  };
  const down = (e: PointerEvent<HTMLDivElement>, resize: boolean) => {
    if (!cameraReady) return;
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, rect, resize };
  };
  const move = (e: PointerEvent<HTMLDivElement>) => {
    const start = drag.current,
      bounds = box.current?.getBoundingClientRect();
    if (!cameraReady || !start || !bounds || imageRatio === null || !bounds.width || !bounds.height)
      return;
    const r = start.rect,
      w = r.x1 - r.x0,
      h = r.y1 - r.y0;
    const dx = (e.clientX - start.x) / bounds.width,
      dy = (e.clientY - start.y) / bounds.height;
    if (start.resize) {
      setRect(resizeTutorialCrop(r, w + dx, imageRatio, areaHeight));
    } else {
      const x = clamp(r.x0 + dx, 1 - w),
        y = clamp(r.y0 + dy, 1 - h);
      setRect({ x0: x, y0: y, x1: x + w, y1: y + h });
    }
    setMessage("");
  };
  const nudge = (dx: number, dy: number) => {
    const w = rect.x1 - rect.x0,
      h = rect.y1 - rect.y0;
    const x = clamp(rect.x0 + dx, 1 - w),
      y = clamp(rect.y0 + dy, 1 - h);
    setRect({ x0: x, y0: y, x1: x + w, y1: y + h });
    setMessage("");
  };
  return (
    <section className="relative z-20 rounded-lg border bg-background p-3 text-foreground [&_button]:min-h-10 [&_button]:rounded-lg [&_button]:border [&_button]:px-3 [&_button]:py-2 [&_button:disabled]:cursor-not-allowed [&_button:disabled]:opacity-50">
      <div className="flex flex-wrap items-center gap-2">
        <strong>
          tutorial 표시 영역 · {TABLET_WIDTH}×{Math.round(areaHeight)} (레이아웃 기준)
        </strong>
        <button disabled={!cameraReady} onClick={center}>
          tutorial 비율로 맞추기
        </button>
        <button disabled={!cameraReady || previewScale <= 0} onClick={() => setPreview(true)}>
          크롭 미리보기
        </button>
        <button
          disabled={!cameraReady}
          onClick={() =>
            setMessage(save(rect) ? "이 브라우저의 tutorial에 적용했습니다" : "저장하지 못했습니다")
          }
        >
          tutorial에 적용
        </button>
        <button
          onClick={() => {
            if (save(null)) {
              if (imageRatio === null) initializedRatio.current = null;
              center();
              setMessage("기존 얼굴 맞춤으로 초기화했습니다");
            } else setMessage("저장하지 못했습니다");
          }}
        >
          초기화
        </button>
      </div>
      <p className="my-2 text-sm">
        점선을 움직이고 오른쪽 아래를 드래그해 크기를 조절하세요. 얼굴 인식은 전체 영상에서
        유지됩니다.
      </p>
      {!cameraReady && (
        <p role="status">카메라 준비 중 · 영상이 준비되면 영역을 조정할 수 있습니다.</p>
      )}
      <div
        className="relative mx-auto w-full max-w-3xl bg-black"
        ref={box}
        style={{ aspectRatio: imageRatio ?? 4 / 3 }}
      >
        <CropView
          crop={FULL}
          step={step}
          predictionStrength={predictionStrength}
          showStats={showStats}
        />
        {cameraReady && (
          <div
            role="group"
            aria-label="tutorial 영역"
            className="absolute touch-none border-2 border-dashed border-yellow-300"
            style={{
              left: `${rect.x0 * 100}%`,
              top: `${rect.y0 * 100}%`,
              width: `${(rect.x1 - rect.x0) * 100}%`,
              height: `${(rect.y1 - rect.y0) * 100}%`,
            }}
            onPointerDown={(e) => down(e, false)}
            onPointerMove={move}
            onPointerUp={() => {
              drag.current = null;
            }}
            onPointerCancel={() => {
              drag.current = null;
            }}
          >
            <div
              role="button"
              tabIndex={0}
              aria-label="영역 크기 조절"
              className="absolute -right-2 -bottom-2 h-8 w-8 touch-none border-2 border-yellow-300 bg-black/60"
              onPointerDown={(e) => down(e, true)}
            />
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-3" aria-label="영역 이동">
        <button disabled={!cameraReady} onClick={() => nudge(-0.01, 0)}>
          ←
        </button>
        <button disabled={!cameraReady} onClick={() => nudge(0.01, 0)}>
          →
        </button>
        <button disabled={!cameraReady} onClick={() => nudge(0, -0.01)}>
          ↑
        </button>
        <button disabled={!cameraReady} onClick={() => nudge(0, 0.01)}>
          ↓
        </button>
        <span role="status">{message}</span>
      </div>
      {previewScale <= 0 && <p>미리보기를 볼 공간이 없습니다. 창을 키워 주세요.</p>}
      {preview && cameraReady && previewScale > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 text-white">
          <button className="absolute top-4 right-4 z-10" onClick={() => setPreview(false)}>
            돌아가기
          </button>
          <div style={{ width: TABLET_WIDTH * previewScale, height: appHeight * previewScale }}>
            <div
              className="relative bg-black"
              style={{
                width: TABLET_WIDTH,
                height: appHeight,
                transform: `scale(${previewScale})`,
                transformOrigin: "top left",
              }}
            >
              <p className="absolute top-6 left-6">
                레이아웃 기준 · {TABLET_WIDTH}×{Math.round(appHeight)}
              </p>
              <div
                className="absolute inset-x-0 overflow-hidden outline-2 outline-yellow-300 outline-dashed"
                style={{ top: TUTORIAL_TOP, bottom: TUTORIAL_BOTTOM }}
              >
                <CropView
                  crop={rect}
                  step={step}
                  predictionStrength={predictionStrength}
                  showStats={showStats}
                />
              </div>
              <p className="absolute inset-x-0 bottom-8 text-center">하단 안내 영역 · 372px</p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
