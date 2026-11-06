"use client";

import { useRef } from "react";

import { distanceHint, faceBoxIn, MIN_DISTANCE_RATIO, useFaceFrame } from "@/features/face";
import { isMirror } from "@/lib/mirror";

/**
 * 얼굴 원 안에 목표(점선 타원)와 지금 얼굴 위치(실선 타원)를 함께 그린다.
 * 미러필름 모드에서는 원 안 영상이 안 보여, 얼마나 가까이·어디로 옮기면 되는지 이것으로만 알 수 있다.
 * 프레임마다 React로 다시 그리지 않고 스타일만 바꾼다. 자리는 faceBoxIn으로 잡아 판정(distanceHint)과 같다.
 * - 일반 모드: 원 안 영상 위 얼굴. 목표는 적정 거리의 최소 크기
 * - 미러필름 모드: 거울에 비친 얼굴(가이드·화장과 같은 자리). 비친 얼굴은 거리와 상관없이 크기가 같아서,
 *   목표는 지금 비친 얼굴과 같은 크기로 원 가운데에 둔다
 */
export function FacePosition({ size }: { size: number }) {
  const targetRef = useRef<HTMLDivElement>(null);
  const faceRef = useRef<HTMLDivElement>(null);

  useFaceFrame((frame) => {
    const target = targetRef.current;
    const face = faceRef.current;
    const circle = target?.parentElement;
    if (!target || !face || !circle) return;
    if (!frame) {
      face.style.opacity = "0";
      return;
    }
    const tracked = frame.trackingState === "tracking" || frame.trackingState === "degraded";
    const mirror = isMirror();
    if (!tracked) {
      face.style.opacity = "0";
      // 미러필름 모드의 목표 크기는 비친 얼굴로 정해, 얼굴이 안 잡히면 목표도 숨긴다
      if (mirror) {
        target.style.opacity = "0";
        return;
      }
    }

    const box = tracked ? faceBoxIn(frame, circle) : null;
    let tw: number;
    let th: number;
    if (mirror && box) {
      tw = box.maxX - box.minX;
      th = box.maxY - box.minY;
    } else {
      const { width: w, height: h } = frame.imageSize;
      tw = ((MIN_DISTANCE_RATIO * w) / Math.min(w, h)) * size;
      th = tw * 1.3;
    }
    Object.assign(target.style, {
      opacity: "1",
      left: `${(size - tw) / 2}px`,
      top: `${(size - th) / 2}px`,
      width: `${tw}px`,
      height: `${th}px`,
    });
    if (!box) return;

    Object.assign(face.style, {
      opacity: "1",
      left: `${box.minX}px`,
      top: `${box.minY}px`,
      width: `${box.maxX - box.minX}px`,
      height: `${box.maxY - box.minY}px`,
    });
    face.dataset.ok = distanceHint(frame, circle) === null ? "1" : "0";
  });

  return (
    <>
      <div
        ref={targetRef}
        className="absolute rounded-[50%] border-2 border-dashed border-white/90 opacity-0"
      />
      <div
        ref={faceRef}
        className="absolute rounded-[50%] border-[3px] border-navy opacity-0 transition-[border-color,box-shadow] duration-200 data-[ok=1]:border-mint data-[ok=1]:shadow-[0_0_0_6px_color-mix(in_srgb,var(--color-mint)_35%,transparent)]"
      />
    </>
  );
}
