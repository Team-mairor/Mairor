"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import {
  eyeDistanceMm,
  fitMirror,
  halfMirror,
  LEFT_IRIS_CENTER,
  loadMirrorFit,
  mirrorScreen,
  RIGHT_IRIS_CENTER,
  saveMirrorFit,
  toScreen,
  useFaceFrame,
  useHiddenVideo,
  type FaceFrame,
  type MirrorFit,
  type MirrorScreen,
} from "@/features/face";
import { GuideOverlay } from "@/features/guide";
import { isMirror, setMirror } from "@/lib/mirror";
import { cn } from "@/lib/utils";

type Px = { x: number; y: number };
type Eyes = [Px, Px];
type Snap = { eyes: Eyes; screen: MirrorScreen };

/** 거울에 비친 홍채 지름(mm). 비친 얼굴은 거리와 상관없이 실제(성인 평균 11.7mm)의 절반이다 */
const REFLECTED_IRIS_MM = 11.7 / 2;

/**
 * 비친 얼굴을 고정해 둘 목표 타원(화면 mm, 카메라 기준). 비친 얼굴은 실제의 절반(폭 약 70mm)이고 거리와 상관없다.
 * 카메라에 가까울수록 가까이 와도 턱이 덜 잘려 위쪽에 둔다. 끌어서 옮길 수 있고 옮긴 자리는 기억한다
 */
const TARGET = { w: 70, h: 95, eyeFromTop: 40 };
/** 타원 눈 높이선 가운데 자리(화면 mm, 카메라 기준)와 TARGET 크기에 곱할 배율 */
type TargetPos = { x: number; y: number; scale: number };
const DEFAULT_TARGET: TargetPos = { x: 0, y: 60, scale: 1 };
/** +·- 한 번에 바꾸는 크기 비율 */
const SIZE_STEP = 1.05;
// ponytail: 거리·위치 측정용 임시 저장. 자리가 확정되면 TARGET 상수로 옮기고 지운다
const TARGET_KEY = "mairor-mirror-target";

function loadTarget(): TargetPos {
  try {
    const saved = JSON.parse(localStorage.getItem(TARGET_KEY) ?? "null") as TargetPos | null;
    if (!saved || !Number.isFinite(saved.x) || !Number.isFinite(saved.y)) return DEFAULT_TARGET;
    return { ...saved, scale: saved.scale > 0 ? saved.scale : 1 };
  } catch {
    return DEFAULT_TARGET;
  }
}

function saveTarget(pos: TargetPos) {
  try {
    localStorage.setItem(TARGET_KEY, JSON.stringify(pos));
  } catch {
    // 저장에 실패해도 이번 실행에는 적용된다
  }
}

/** 이 화면 기준 두 눈 위치. fit이 없으면 보정 없이 계산한다 */
function eyesOf(frame: FaceFrame, screen: MirrorScreen, fit = { scale: 1, dx: 0, dy: 0 }): Eyes {
  const reflected = halfMirror(frame, screen, fit);
  const at = (i: number) => toScreen(reflected.frame.landmarks[i], frame.imageSize, reflected.view);
  return [at(RIGHT_IRIS_CENTER), at(LEFT_IRIS_CENTER)];
}

/**
 * 끌어서 옮기는 맞춤 점. 보이는 원은 비친 홍채 크기(ring)라 원 테두리를 홍채 테두리에 맞추면 되고,
 * 누르는 자리는 손가락에 맞게 크게 둔다. 누르면 선택돼 +·-로 크기를 바꾼다
 */
function Dot({
  at,
  ring,
  label,
  selected,
  onSelect,
  onMove,
}: {
  at: Px;
  ring: number;
  label: string;
  selected: boolean;
  onSelect: () => void;
  onMove: (e: PointerEvent) => void;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={selected}
      className="absolute flex size-16 -translate-x-1/2 -translate-y-1/2 touch-none items-center justify-center"
      style={{ left: at.x, top: at.y }}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        onSelect();
      }}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) onMove(e.nativeEvent);
      }}
    >
      {/* 누르는 자리보다 커져도 찌그러지지 않게 줄어들지 않게 한다 */}
      <span
        className={cn(
          "flex shrink-0 items-center justify-center rounded-full border-2",
          selected ? "border-mint" : "border-white",
        )}
        style={{ width: ring, height: ring }}
      >
        <span className="size-1 rounded-full bg-white" />
      </span>
    </button>
  );
}

const isNoFit = (fit: MirrorFit) => fit.scale === 1 && fit.dx === 0 && fit.dy === 0;

/**
 * 하프미러 맞춤 (CAMERA-003). 거울에 비친 두 눈동자 위로 점을 옮겨 저장하면,
 * 기기 상수·눈 사이 거리·주로 쓰는 눈 때문에 남는 가이드·화장 위치 오차를 배율·이동으로 보정한다.
 * 거울상은 화면 뒤에 있어 두 눈에 가로로 다르게 겹치므로(눈마다 약 IOD/4), 평소처럼 두 눈을 뜨고 맞춰야
 * 주로 쓰는 눈 기준의 이동이 저장된다
 */
export default function MirrorFitPage() {
  const router = useRouter();
  const areaRef = useRef<HTMLDivElement>(null);
  const [dots, setDots] = useState<Eyes | null>(null);
  // 최신 프레임의 보정 전 눈 위치
  const latest = useRef<Snap | null>(null);
  // 점마다 마지막으로 옮긴 순간의 보정 전 눈 위치. 점을 맞출 때와 저장을 누를 때 고개 위치가 달라도
  // (가까이 다가가 맞춘 뒤 물러나 저장해도) 맞춘 순간끼리 비교한다. 비친 위치 오차는 거리와 상관없다
  const snaps = useRef<[Snap, Snap] | null>(null);
  const [saved, setSaved] = useState(false);
  /** 지금 저장돼 있는 맞춤. 얼굴이 처음 잡힐 때 읽는다 */
  const [stored, setStored] = useState<MirrorFit | null>(null);
  /** 목표 타원을 그릴 화면 정보 */
  const [screen, setScreen] = useState<MirrorScreen | null>(null);
  const [target, setTarget] = useState(DEFAULT_TARGET);
  /** 타원을 잡은 자리와 타원 눈 높이선 가운데의 차이(px). 잡은 자리가 손가락을 따라가게 한다 */
  const grab = useRef<Px | null>(null);
  /** 눈동자 원 지름에 곱할 배율 */
  const [irisScale, setIrisScale] = useState(1);
  /** +·-로 크기를 바꿀 대상. 눈동자나 타원을 누르면 바뀐다 */
  const [selected, setSelected] = useState<"eyes" | "face">("eyes");
  /** 눈–화면 거리. 프레임마다 바뀌어 React로 다시 그리지 않고 글자만 바꾼다 */
  const distanceRef = useRef<HTMLSpanElement>(null);

  // 비친 얼굴에 맞추는 화면이라 카메라 영상을 숨기고, 이 화면에 있는 동안은 미러필름 모드로 둔다.
  // 저장된 모드 설정은 바꾸지 않고, 나가면 들어오기 전 모드로 돌린다
  useHiddenVideo();
  useEffect(() => {
    const before = isMirror();
    setMirror(true);
    if (areaRef.current) setScreen(mirrorScreen(areaRef.current));
    setTarget(loadTarget());
    return () => setMirror(before);
  }, []);

  useFaceFrame((frame) => {
    const area = areaRef.current;
    const label = distanceRef.current;
    if (label) {
      label.textContent =
        frame?.trackingState === "tracking" ? `${(eyeDistanceMm(frame) / 10).toFixed(1)}cm` : "–";
    }
    if (!area || frame?.trackingState !== "tracking") return;
    const screen = mirrorScreen(area);
    // 들어온 순간엔 레이아웃(미러 전환·주소창)이 덜 잡혀 있을 수 있어, 눈동자와 같은 기준으로 타원도 맞춘다
    setScreen((prev) =>
      prev &&
      prev.originX === screen.originX &&
      prev.originY === screen.originY &&
      prev.pxPerMm === screen.pxPerMm
        ? prev
        : screen,
    );
    const snap = { eyes: eyesOf(frame, screen), screen };
    latest.current = snap;
    // 처음에는 지금 보정으로 계산한 자리에 점을 둔다
    if (!snaps.current) {
      snaps.current = [snap, snap];
      const fit = loadMirrorFit();
      setStored(fit);
      setDots(eyesOf(frame, screen, fit));
    }
  });

  /** 포인터 자리를 이 화면 요소 안 px로 */
  const toArea = (e: { clientX: number; clientY: number }): Px | null => {
    const area = areaRef.current;
    if (!area) return null;
    const rect = area.getBoundingClientRect();
    const zoom = rect.width / area.clientWidth || 1;
    return { x: (e.clientX - rect.left) / zoom, y: (e.clientY - rect.top) / zoom };
  };

  const move = (index: 0 | 1, e: PointerEvent) => {
    const p = toArea(e);
    if (!p) return;
    if (snaps.current && latest.current) snaps.current[index] = latest.current;
    setSaved(false);
    setDots((prev) => prev && (index === 0 ? [p, prev[1]] : [prev[0], p]));
  };

  const save = () => {
    const [a, b] = snaps.current ?? [];
    if (!dots || !a || !b) return;
    const fit = fitMirror([a.eyes[0], b.eyes[1]], dots, b.screen);
    saveMirrorFit(fit);
    setStored(loadMirrorFit());
    setSaved(true);
  };

  const reset = () => {
    saveMirrorFit(null);
    saveTarget(DEFAULT_TARGET);
    setTarget(DEFAULT_TARGET);
    setIrisScale(1);
    setStored(loadMirrorFit());
    const snap = latest.current;
    snaps.current = snap ? [snap, snap] : null;
    setDots(snap?.eyes ?? null);
    setSaved(false);
  };

  const ring = screen ? Math.max(8, REFLECTED_IRIS_MM * screen.pxPerMm * irisScale) : 12;
  const faceW = TARGET.w * target.scale;
  const faceH = TARGET.h * target.scale;

  const resize = (step: number) => {
    if (selected === "eyes") setIrisScale((s) => s * step);
    else
      setTarget((t) => {
        const next = { ...t, scale: t.scale * step };
        saveTarget(next);
        return next;
      });
  };

  return (
    <main className="relative flex flex-1 flex-col">
      <div ref={areaRef} className="absolute inset-0">
        {/* 저장한 보정으로 그린 얼굴 윤곽. 비친 얼굴에 겹치면 맞춤이 된 것이다 */}
        <GuideOverlay step={null} face />
        {screen && (
          // 비친 얼굴을 넣어 둘 자리. 가운데 가로선이 눈 높이고, 끌어서 옮긴다
          <div
            aria-label="얼굴 목표 타원"
            className={cn(
              "absolute touch-none rounded-[50%] border-[3px] border-dashed",
              selected === "face" ? "border-mint" : "border-white",
            )}
            style={{
              left: screen.originX + (target.x - faceW / 2) * screen.pxPerMm,
              top: screen.originY + (target.y - TARGET.eyeFromTop * target.scale) * screen.pxPerMm,
              width: faceW * screen.pxPerMm,
              height: faceH * screen.pxPerMm,
            }}
            onPointerDown={(e) => {
              const p = toArea(e);
              if (!p) return;
              e.currentTarget.setPointerCapture(e.pointerId);
              setSelected("face");
              grab.current = {
                x: p.x - (screen.originX + target.x * screen.pxPerMm),
                y: p.y - (screen.originY + target.y * screen.pxPerMm),
              };
            }}
            onPointerMove={(e) => {
              const p = toArea(e);
              if (!p || !grab.current || !e.currentTarget.hasPointerCapture(e.pointerId)) return;
              setTarget({
                ...target,
                x: (p.x - grab.current.x - screen.originX) / screen.pxPerMm,
                y: (p.y - grab.current.y - screen.originY) / screen.pxPerMm,
              });
            }}
            onPointerUp={() => {
              grab.current = null;
              saveTarget(target);
            }}
          >
            <div
              className="absolute inset-x-0 border-t-2 border-dashed border-white"
              style={{ top: TARGET.eyeFromTop * target.scale * screen.pxPerMm }}
            />
          </div>
        )}
        {dots && (
          <>
            {([0, 1] as const).map((i) => (
              <Dot
                key={i}
                at={dots[i]}
                ring={ring}
                label={i === 0 ? "오른쪽 눈 맞춤 점" : "왼쪽 눈 맞춤 점"}
                selected={selected === "eyes"}
                onSelect={() => setSelected("eyes")}
                onMove={(e) => move(i, e)}
              />
            ))}
          </>
        )}
      </div>

      <div className="relative mx-6 mt-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-bold">거울 맞추기</h1>
          <p className="mt-2 text-[17px] leading-relaxed text-mute">
            {dots
              ? "두 눈을 모두 뜬 채 고개를 움직이지 말고, 거울에 비친 두 눈동자 위로 동그라미를 옮겨 주세요"
              : "얼굴을 찾고 있어요. 화면 정면에 앉아 주세요"}
          </p>
          <p className="mt-1 text-[15px] text-mute tabular">
            눈–화면 거리 <span ref={distanceRef}>–</span>
          </p>
          <p className="mt-1 text-[15px] text-mute tabular">
            타원 눈 높이 카메라에서 {target.y.toFixed(0)}mm 아래 · 가로 {target.x.toFixed(0)}mm
          </p>
          {stored && (
            <p className="mt-1 text-[15px] text-mute tabular">
              {isNoFit(stored)
                ? "저장된 맞춤 없음"
                : `저장된 맞춤 · 크기 ${stored.scale.toFixed(2)}배 · 이동 ${stored.dx.toFixed(1)}, ${stored.dy.toFixed(1)}mm`}
            </p>
          )}
        </div>
      </div>

      <div className="relative mx-6 mt-auto mb-3 flex items-center justify-center gap-3">
        <span className="text-[17px] text-mute">
          {selected === "eyes" ? "눈동자 크기" : "얼굴 타원 크기"}
        </span>
        <PillButton
          variant="outline"
          className="w-16 border-white text-white"
          aria-label="작게"
          onClick={() => resize(1 / SIZE_STEP)}
        >
          −
        </PillButton>
        <PillButton
          variant="outline"
          className="w-16 border-white text-white"
          aria-label="크게"
          onClick={() => resize(SIZE_STEP)}
        >
          +
        </PillButton>
      </div>

      <div className="relative mx-6 mb-8 flex gap-3">
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
