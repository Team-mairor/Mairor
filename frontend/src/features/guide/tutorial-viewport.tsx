"use client";

import { useCallback, useEffect, useMemo, useRef, useSyncExternalStore } from "react";

import { useCamera, useFaceRender, type NormalizedRect } from "@/features/face";
import { isMirror, subscribeMirror } from "@/lib/mirror";

import { GuideOverlay } from "./guide-overlay";
import {
  CROP_KEY,
  cropTransform,
  TUTORIAL_BOTTOM,
  TUTORIAL_TOP,
  validCrop,
  writeTutorialCrop,
} from "./tutorial-crop";
import type { GuideStep } from "./types";

const EVENT = "tutorial-crop-change";
const subscribe = (change: () => void) => {
  window.addEventListener("storage", change);
  window.addEventListener(EVENT, change);
  return () => {
    window.removeEventListener("storage", change);
    window.removeEventListener(EVENT, change);
  };
};
const snapshot = () => {
  try {
    return localStorage.getItem(CROP_KEY);
  } catch {
    return null;
  }
};

export function useTutorialCrop() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => null);
  const crop = useMemo(() => {
    try {
      const value: unknown = JSON.parse(raw ?? "null");
      return validCrop(value) ? value : null;
    } catch {
      return null;
    }
  }, [raw]);
  const save = useCallback((value: NormalizedRect | null) => {
    if (value && !validCrop(value)) return false;
    try {
      if (!writeTutorialCrop(localStorage, value)) return false;
      window.dispatchEvent(new Event(EVENT));
      return true;
    } catch {
      return false;
    }
  }, []);
  return { crop, save };
}

/** 영상과 가이드에 같은 크롭 변환을 사용한다. 추적 입력은 바꾸지 않는다. */
export function CropView({
  crop,
  step,
  video = true,
  face = false,
  predictionStrength,
  showStats,
}: {
  crop: NormalizedRect;
  step: GuideStep | null;
  video?: boolean;
  face?: boolean;
  predictionStrength?: number;
  showStats?: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const cropRef = useRef(crop);
  const { videoRef } = useCamera();
  useEffect(() => {
    cropRef.current = crop;
  }, [crop]);
  useFaceRender(() => {
    const crop = cropRef.current;
    const c = canvas.current,
      source = videoRef.current;
    if (!c || !source || !source.videoWidth || !source.videoHeight) return;
    const image = { width: source.videoWidth, height: source.videoHeight };
    const ratio = window.devicePixelRatio || 1;
    const width = c.clientWidth,
      height = c.clientHeight;
    const w = Math.round(width * ratio),
      h = Math.round(height * ratio);
    if (c.width !== w || c.height !== h) {
      c.width = w;
      c.height = h;
    }
    const ctx = c.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    if (!video || source.readyState < 2) return;
    const v = cropTransform(image, { width, height }, crop);
    ctx.save();
    ctx.beginPath();
    ctx.rect(
      crop.x0 * image.width * v.scale + v.offsetX,
      crop.y0 * image.height * v.scale + v.offsetY,
      (crop.x1 - crop.x0) * image.width * v.scale,
      (crop.y1 - crop.y0) * image.height * v.scale,
    );
    ctx.clip();
    ctx.translate(v.offsetX + image.width * v.scale, v.offsetY);
    ctx.scale(-v.scale, v.scale);
    ctx.drawImage(source, 0, 0);
    ctx.restore();
  });
  return (
    <div className="relative h-full w-full overflow-hidden">
      <canvas ref={canvas} className="absolute inset-0 h-full w-full mirror:invisible" />
      <GuideOverlay
        step={step}
        crop={crop}
        face={face}
        predictionStrength={predictionStrength}
        showStats={showStats}
      />
    </div>
  );
}

/**
 * 튜토리얼 화면의 얼굴 자리.
 * - 미러필름: 거울에 비친 얼굴 자리에 가이드만 그린다
 * - 일반: 카메라 영상 위 같은 자리에 가이드를 그린다. 크롭이 있으면 크롭한 영상과 가이드를 함께 그린다
 */
export function TutorialViewport({ step }: { step: GuideStep | null }) {
  const { crop } = useTutorialCrop();
  const mirror = useSyncExternalStore(subscribeMirror, isMirror, () => false);
  const { setShowVideo } = useCamera();
  // 크롭은 따로 그린 영상을 보여 주므로 전체 카메라 영상을 숨긴다. 미러필름에서는 CSS가 영상을 숨긴다
  useEffect(() => {
    setShowVideo(!crop);
    return () => setShowVideo(true);
  }, [crop, setShowVideo]);

  // 일반은 전체 카메라 영상과 같은 칸에 그려야 위치가 맞는다.
  // 미러필름은 위·아래 패널도 거울이라 띠로 자르면 그 뒤에 비친 눈썹·입술 가이드가 잘린다
  if (mirror || !crop) return <GuideOverlay step={step} />;
  return (
    <div
      className="absolute inset-x-0 overflow-hidden"
      style={{ top: TUTORIAL_TOP, bottom: TUTORIAL_BOTTOM }}
    >
      <CropView crop={crop} step={step} />
    </div>
  );
}
