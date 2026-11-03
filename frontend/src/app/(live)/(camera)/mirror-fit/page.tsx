"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { PillButton } from "@/components/ui/pill-button";
import {
  fitMirror,
  halfMirror,
  LEFT_IRIS_CENTER,
  loadMirrorFit,
  mirrorScreen,
  RIGHT_IRIS_CENTER,
  saveMirrorFit,
  toScreen,
  useFaceFrame,
  type FaceFrame,
  type MirrorScreen,
} from "@/features/face";
import { GuideOverlay } from "@/features/guide";

type Px = { x: number; y: number };
type Eyes = [Px, Px];

/** 이 화면 기준 두 눈 위치. fit이 없으면 보정 없이 계산한다 */
function eyesOf(frame: FaceFrame, screen: MirrorScreen, fit = { scale: 1, dx: 0, dy: 0 }): Eyes {
  const reflected = halfMirror(frame, screen, fit);
  const at = (i: number) => toScreen(reflected.frame.landmarks[i], frame.imageSize, reflected.view);
  return [at(RIGHT_IRIS_CENTER), at(LEFT_IRIS_CENTER)];
}

/** 끌어서 옮기는 맞춤 점. 가운데가 비어 있어 점 안으로 비친 눈동자가 보인다 */
function Dot({ at, label, onMove }: { at: Px; label: string; onMove: (e: PointerEvent) => void }) {
  return (
    <button
      type="button"
      aria-label={label}
      className="absolute flex size-16 -translate-x-1/2 -translate-y-1/2 touch-none items-center justify-center rounded-full border-[3px] border-white"
      style={{ left: at.x, top: at.y }}
      onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) onMove(e.nativeEvent);
      }}
    >
      <span className="size-2 rounded-full bg-white" />
    </button>
  );
}

/**
 * 하프미러 맞춤 (CAMERA-003). 거울에 비친 두 눈동자 위로 점을 옮겨 저장하면,
 * 기기 상수·눈 사이 거리·주로 쓰는 눈 때문에 남는 가이드·화장 위치 오차를 배율·이동으로 보정한다.
 */
export default function MirrorFitPage() {
  const router = useRouter();
  const areaRef = useRef<HTMLDivElement>(null);
  const [dots, setDots] = useState<Eyes | null>(null);
  // 저장할 때 쓸 최신 프레임의 보정 전 눈 위치
  const latest = useRef<{ eyes: Eyes; screen: MirrorScreen } | null>(null);
  const [saved, setSaved] = useState(false);

  useFaceFrame((frame) => {
    const area = areaRef.current;
    if (!area || frame?.trackingState !== "tracking") return;
    const screen = mirrorScreen(area);
    latest.current = { eyes: eyesOf(frame, screen), screen };
    // 처음에는 지금 보정으로 계산한 자리에 점을 둔다
    setDots((prev) => prev ?? eyesOf(frame, screen, loadMirrorFit()));
  });

  const move = (index: 0 | 1) => (e: PointerEvent) => {
    const area = areaRef.current;
    if (!area) return;
    const rect = area.getBoundingClientRect();
    const zoom = rect.width / area.clientWidth || 1;
    const p = { x: (e.clientX - rect.left) / zoom, y: (e.clientY - rect.top) / zoom };
    setSaved(false);
    setDots((prev) => prev && (index === 0 ? [p, prev[1]] : [prev[0], p]));
  };

  const save = () => {
    if (!dots || !latest.current) return;
    saveMirrorFit(fitMirror(latest.current.eyes, dots, latest.current.screen));
    setSaved(true);
  };

  const reset = () => {
    saveMirrorFit(null);
    setDots(latest.current?.eyes ?? null);
    setSaved(false);
  };

  return (
    <main className="relative flex flex-1 flex-col">
      <div ref={areaRef} className="absolute inset-0">
        {/* 저장한 보정으로 그린 얼굴 윤곽. 비친 얼굴에 겹치면 맞춤이 된 것이다 */}
        <GuideOverlay step={null} face />
        {dots && (
          <>
            <Dot at={dots[0]} label="오른쪽 눈 맞춤 점" onMove={move(0)} />
            <Dot at={dots[1]} label="왼쪽 눈 맞춤 점" onMove={move(1)} />
          </>
        )}
      </div>

      <div className="relative mx-6 mt-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-bold">거울 맞추기</h1>
          <p className="mt-2 text-[17px] leading-relaxed text-mute">
            {dots
              ? "고개를 움직이지 말고, 거울에 비친 두 눈동자 위로 동그라미를 옮겨 주세요"
              : "얼굴을 찾고 있어요. 화면 정면에 앉아 주세요"}
          </p>
        </div>
        <MirrorToggle />
      </div>

      <div className="relative mx-6 mt-auto mb-8 flex gap-3">
        <PillButton variant="outline" className="flex-1 border-white text-white" onClick={reset}>
          처음으로
        </PillButton>
        <PillButton className="flex-1" disabled={!dots} onClick={save}>
          {saved ? "저장했어요" : "저장"}
        </PillButton>
        <PillButton variant="white" className="flex-1" onClick={() => router.back()}>
          돌아가기
        </PillButton>
      </div>
    </main>
  );
}
