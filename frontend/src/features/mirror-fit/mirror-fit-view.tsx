"use client";

import { useRef, useState, type PointerEvent } from "react";

import { PillButton } from "@/components/ui/pill-button";
import {
  eyeDistanceMm,
  fitMirror,
  halfMirror,
  LEFT_IRIS_CENTER,
  loadMirrorFit,
  mirrorScreen,
  openEye,
  RIGHT_IRIS_CENTER,
  saveMirrorFit,
  StartCamera,
  toScreen,
  useFaceFrame,
  type EyeSide,
  type FaceFrame,
  type MirrorFit,
  type MirrorScreen,
} from "@/features/face";
import { GuideOverlay } from "@/features/guide";
import { CameraErrorNote } from "@/features/live";

type Px = { x: number; y: number };
type Eyes = [Px, Px];
type Snap = { eyes: Eyes; screen: MirrorScreen; frame: FaceFrame };

/** 비친 홍채 지름(mm). 실제(평균 11.7mm)의 절반 */
const REFLECTED_IRIS_MM = 11.7 / 2;

/** 지금 얼굴의 두 눈 간격(px)·기울기(rad)와 원 지름 */
type Shape = { gap: number; angle: number; ring: number };

/** 처음 두 원 간격 배율. 일부러 좁게 시작해 각자 +로 눈동자에 맞추게 한다 */
const START_SCALE = 0.6;

/** 간격 −·+ 한 번에 바꾸는 비율 */
const GAP_STEP = 1.04;

const midOf = ([a, b]: Eyes): Px => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

const shapeOf = ([a, b]: Eyes, screen: MirrorScreen): Shape => {
  const [l, r] = a.x <= b.x ? [a, b] : [b, a];
  return {
    gap: Math.hypot(r.x - l.x, r.y - l.y),
    angle: Math.atan2(r.y - l.y, r.x - l.x),
    ring: Math.max(8, REFLECTED_IRIS_MM * screen.pxPerMm),
  };
};

/** 이 화면 기준 두 눈 위치. fit이 없으면 보정 없이 계산한다. viewer는 보는 눈(정하지 않으면 fit에서 고른다) */
function eyesOf(
  frame: FaceFrame,
  screen: MirrorScreen,
  fit: MirrorFit = { scale: 1, dx: 0, dy: 0 },
  viewer?: EyeSide | null,
): Eyes {
  const reflected =
    viewer === undefined
      ? halfMirror(frame, screen, fit)
      : halfMirror(frame, screen, fit, undefined, undefined, viewer);
  const at = (i: number) => toScreen(reflected.frame.landmarks[i], frame.imageSize, reflected.view);
  return [at(RIGHT_IRIS_CENTER), at(LEFT_IRIS_CENTER)];
}

/** 두 눈동자 원과 가운데 십자. 함께 움직이고 간격·기울기는 지금 얼굴을 따른다 */
function EyeGuide({
  at,
  shape,
  scale,
}: {
  at: Px;
  shape: Shape;
  /** 맞춘 간격 배율 */ scale: number;
}) {
  const { angle, ring } = shape;
  const gap = shape.gap * scale;
  // 원을 담는 칸. 칸 가운데가 원 중심이라 두 원 중심 간격이 늘 gap이 된다
  const slot = Math.max(ring, 64);
  const reach = gap + slot;
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute flex items-center justify-between"
      style={{
        left: at.x - reach / 2,
        top: at.y - slot / 2,
        width: reach,
        height: slot,
        transform: `rotate(${angle}rad)`,
      }}
    >
      {[0, 1].map((i) => (
        <span
          key={i}
          className="relative flex shrink-0 items-center justify-center"
          style={{ width: slot }}
        >
          <span
            className="shrink-0 rounded-full border-2 border-mint"
            style={{ width: ring, height: ring }}
          />
        </span>
      ))}
      <span className="absolute top-1/2 left-1/2 h-0.5 w-5 -translate-1/2 bg-mint" />
      <span className="absolute top-1/2 left-1/2 h-5 w-0.5 -translate-1/2 bg-mint" />
    </div>
  );
}

/** 표시를 잡은 것으로 보는 거리(px). 이보다 멀리 누르면 그 자리로 옮긴다 */
const GRAB_PX = 48;

const isNoFit = (fit: MirrorFit) => fit.scale === 1 && fit.dx === 0 && fit.dy === 0;

/** 거리·저장값 숫자는 개발 중에만 보인다 */
const SHOW_NUMBERS = process.env.NODE_ENV !== "production";

/**
 * 하프미러 맞춤. 두 눈으로 보면 표시가 겹쳐 보여 주로 쓰는 눈으로 위치·간격을 맞춘다.
 * 저장하면 바로 닫는다. first면 처음 맞추는 흐름이라 제목을 보이고 취소 대신 「나중에 할게요」를 둔다
 */
export function MirrorFitView({
  first = false,
  onClose,
}: {
  first?: boolean;
  onClose: () => void;
}) {
  const areaRef = useRef<HTMLDivElement>(null);
  const [cross, setCross] = useState<Px | null>(null);
  const [shape, setShape] = useState<Shape | null>(null);
  /** 두 원 간격 배율. 앞사람이 맞춘 배율을 물려받지 않게 늘 좁게 시작한다 */
  const [scale, setScale] = useState(START_SCALE);
  /** 간격을 한 번이라도 맞췄는지. 좁게 시작한 0.6배가 그대로 저장되지 않게 한다 */
  const [widened, setWidened] = useState(false);
  // 최신 프레임의 보정 전 눈 위치
  const latest = useRef<Snap | null>(null);
  // 표시를 마지막으로 옮긴 순간의 눈 위치. 저장 때 고개가 움직였어도 이 순간과 비교한다
  const snap = useRef<Snap | null>(null);
  /** 지금 저장돼 있는 맞춤. 얼굴이 처음 잡힐 때 읽는다 */
  const [stored, setStored] = useState<MirrorFit | null>(null);
  /** 눈–화면 거리. 프레임마다 글자만 바꾼다 */
  const distanceRef = useRef<HTMLSpanElement>(null);

  useFaceFrame((frame) => {
    const area = areaRef.current;
    const label = distanceRef.current;
    if (label) {
      label.textContent =
        frame?.trackingState === "tracking" ? `${(eyeDistanceMm(frame) / 10).toFixed(1)}cm` : "–";
    }
    if (!area || frame?.trackingState !== "tracking") return;
    const screen = mirrorScreen(area);
    const now = { eyes: eyesOf(frame, screen, undefined, null), screen, frame };
    latest.current = now;
    const next = shapeOf(now.eyes, screen);
    setShape((prev) =>
      prev &&
      Math.abs(prev.gap - next.gap) < 0.5 &&
      Math.abs(prev.angle - next.angle) < 0.005 &&
      prev.ring === next.ring
        ? prev
        : next,
    );
    // 처음에는 지금 보정으로 계산한 자리에 십자를 둔다
    if (!snap.current) {
      snap.current = now;
      const fit = loadMirrorFit();
      setStored(fit);
      setCross(midOf(eyesOf(frame, screen, fit)));
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

  /** 잡은 자리와 표시 가운데의 차이(px) */
  const grab = useRef<Px | null>(null);
  /** 맞추는 동안 뜬 눈. 한쪽만 감고 맞추므로 그때 뜬 눈이 주로 쓰는 눈이다 */
  // 아무것도 건드리지 않고 저장해도 예전 보는 눈이 빠지지 않게 저장된 눈으로 시작한다
  const dominant = useRef<EyeSide | null>(loadMirrorFit().eye ?? null);
  const noteEye = () => {
    const frame = latest.current?.frame;
    const open = frame && openEye(frame);
    if (open) dominant.current = open;
  };
  // 표시 근처를 누르면 잡아 끌고, 먼 곳을 누르면 그 자리로 옮긴다.
  // 처음 자리를 잘못 잡아 표시가 화면 밖에 있어도 눈 사이를 누르면 된다
  const grabCross = (e: PointerEvent) => {
    const p = toArea(e);
    if (!p || !cross || !shape) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const near =
      Math.hypot(p.x - cross.x, p.y - cross.y) < Math.max(GRAB_PX, (shape.gap * scale) / 2);
    grab.current = near ? { x: p.x - cross.x, y: p.y - cross.y } : { x: 0, y: 0 };
    if (!near) moveCross(e);
  };
  // 옮긴 순간의 얼굴 위치를 기준으로 삼는다
  const moveCross = (e: PointerEvent) => {
    const p = toArea(e);
    const off = grab.current;
    if (!p || !off) return;
    if (latest.current) snap.current = latest.current;
    noteEye();
    setCross({ x: p.x - off.x, y: p.y - off.y });
  };

  // 가운데 십자는 두고 두 원만 양쪽으로 똑같이 벌리거나 좁힌다
  const widen = (step: number) => {
    noteEye();
    setWidened(true);
    setScale((s) => s * step);
  };

  const save = () => {
    const base = snap.current;
    if (!cross || !base) return;
    // 뜬 눈을 알면 그 눈에서 본 자리 기준으로 맞춰, 나중에 다른 눈으로 봐도 따라가게 한다
    const eye = dominant.current ?? undefined;
    const predicted = eye ? eyesOf(base.frame, base.screen, undefined, eye) : base.eyes;
    saveMirrorFit(fitMirror(midOf(predicted), cross, base.screen, scale, eye));
    onClose();
  };

  return (
    <div className="relative flex flex-1 flex-col">
      <StartCamera />
      <div
        ref={areaRef}
        className="absolute inset-0 touch-none"
        onPointerDown={grabCross}
        onPointerMove={(e) => {
          if (e.currentTarget.hasPointerCapture(e.pointerId)) moveCross(e);
        }}
      >
        {/* 저장한 보정으로 그린 얼굴 윤곽 */}
        <GuideOverlay step={null} face />
        {cross && shape && <EyeGuide at={cross} shape={shape} scale={scale} />}
      </div>

      {/* (live) 레이아웃은 카메라 오류 화면을 띄우지 않는다 */}
      <CameraErrorNote />

      {/* 눈 높이를 가리지 않게 안내는 아래에 둔다 */}
      <div className="pointer-events-none relative mx-6 mt-auto mb-4 flex flex-col gap-2">
        {first && (
          <h1 className="text-[22px] font-bold text-white">거울에 비친 얼굴에 가이드를 맞출게요</h1>
        )}
        {cross ? (
          <ol className="list-decimal pl-5 text-[17px] leading-relaxed text-mute">
            <li>두 눈을 뜬 채 거울 속 두 눈 사이를 누르거나 십자를 끌어 놓아 주세요</li>
            <li>한쪽 눈씩 감아 보세요. 십자가 덜 움직이는 쪽이 주로 쓰는 눈이에요</li>
            <li>
              그 눈만 뜨고 십자를 다시 두 눈 사이에 맞춘 뒤, 간격 −·+로 두 원을 눈동자에 맞추고
              저장해 주세요
            </li>
          </ol>
        ) : (
          <p className="text-[17px] leading-relaxed text-mute">
            얼굴을 찾고 있어요. 화면 정면에 앉아 주세요
          </p>
        )}
        {SHOW_NUMBERS && (
          <p className="text-[15px] text-mute tabular">
            눈–화면 거리 <span ref={distanceRef}>–</span>
            {stored &&
              (isNoFit(stored)
                ? " · 저장된 맞춤 없음"
                : ` · 저장된 맞춤 · ${stored.eye ? `${stored.eye === "left" ? "왼" : "오른"}눈 · ` : ""}크기 ${stored.scale.toFixed(2)}배 · 이동 ${stored.dx.toFixed(1)}, ${stored.dy.toFixed(1)}mm`)}
          </p>
        )}
      </div>

      <div className="relative mx-6 mb-3 flex items-center justify-center gap-3">
        <span className="text-[17px] text-mute">간격</span>
        <PillButton
          variant="outline"
          className="w-16 border-white text-white"
          aria-label="간격 좁게"
          disabled={!cross}
          onClick={() => widen(1 / GAP_STEP)}
        >
          −
        </PillButton>
        <PillButton
          variant="outline"
          className="w-16 border-white text-white"
          aria-label="간격 넓게"
          disabled={!cross}
          onClick={() => widen(GAP_STEP)}
        >
          +
        </PillButton>
      </div>

      <div className="relative mx-6 mb-8 flex gap-3">
        <PillButton className="flex-1" disabled={!cross || !widened} onClick={save}>
          저장
        </PillButton>
        <PillButton variant="outline" className="flex-1 border-white text-white" onClick={onClose}>
          {first ? "나중에 할게요" : "취소"}
        </PillButton>
      </div>
    </div>
  );
}
