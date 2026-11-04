"use client";

import { useRef } from "react";

import { distanceHint, faceBox, MIN_DISTANCE_RATIO, useFaceFrame } from "@/features/face";

/**
 * 얼굴 원 안에 목표 크기(점선 타원)와 지금 얼굴 위치(실선 타원)를 함께 그린다.
 * 미러필름 모드에서는 원 안 영상이 안 보여, 얼마나 가까이·어디로 옮기면 되는지 이것으로만 알 수 있다.
 * 프레임마다 React로 다시 그리지 않고 스타일만 바꾼다.
 * 원은 영상 가운데 정사각형을 거울처럼 뒤집어 보여 주므로(FaceVideo) 같은 방식으로 옮겨 그린다.
 */
export function FacePosition({ size }: { size: number }) {
  const targetRef = useRef<HTMLDivElement>(null);
  const faceRef = useRef<HTMLDivElement>(null);

  useFaceFrame((frame) => {
    const target = targetRef.current;
    const face = faceRef.current;
    if (!target || !face) return;
    if (!frame) {
      face.style.opacity = "0";
      return;
    }
    const { width: w, height: h } = frame.imageSize;
    const side = Math.min(w, h);
    const toX = (x: number) => size - ((x * w - (w - side) / 2) / side) * size;
    const toY = (y: number) => ((y * h - (h - side) / 2) / side) * size;

    // 적정 거리의 최소 폭. 얼굴이 이 점선을 채우면 거리가 맞는다
    const tw = ((MIN_DISTANCE_RATIO * w) / side) * size;
    const th = tw * 1.3;
    Object.assign(target.style, {
      opacity: "1",
      left: `${(size - tw) / 2}px`,
      top: `${(size - th) / 2}px`,
      width: `${tw}px`,
      height: `${th}px`,
    });

    const tracked = frame.trackingState === "tracking" || frame.trackingState === "degraded";
    if (!tracked) {
      face.style.opacity = "0";
      return;
    }
    const box = faceBox(frame);
    const left = toX(box.maxX);
    const top = toY(box.minY);
    Object.assign(face.style, {
      opacity: "1",
      left: `${left}px`,
      top: `${top}px`,
      width: `${toX(box.minX) - left}px`,
      height: `${toY(box.maxY) - top}px`,
    });
    face.dataset.ok = distanceHint(frame) === null ? "1" : "0";
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
