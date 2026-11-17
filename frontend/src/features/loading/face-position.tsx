"use client";

import { useRef } from "react";

import { distanceHint, faceBoxIn, useFaceFrame } from "@/vision/face";

/**
 * 얼굴 원 안에 지금 얼굴 위치(실선 타원)를 그린다. 자리는 판정(distanceHint)과 같은 faceBoxIn이다.
 * 프레임마다 React로 다시 그리지 않고 스타일만 바꾼다
 */
export function FacePosition() {
  const faceRef = useRef<HTMLDivElement>(null);

  useFaceFrame((frame) => {
    const face = faceRef.current;
    const circle = face?.parentElement;
    if (!face || !circle) return;
    const tracked = frame?.trackingState === "tracking" || frame?.trackingState === "degraded";
    if (!frame || !tracked) {
      face.style.opacity = "0";
      return;
    }
    const box = faceBoxIn(frame, circle);
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
    <div
      ref={faceRef}
      className="absolute rounded-[50%] border-[3px] border-navy opacity-0 transition-[border-color,box-shadow] duration-200 data-[ok=1]:border-mint data-[ok=1]:shadow-[0_0_0_6px_color-mix(in_srgb,var(--color-mint)_35%,transparent)]"
    />
  );
}
