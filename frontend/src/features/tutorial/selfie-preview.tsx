"use client";

import { useRef, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { useCamera, useFaceRender } from "@/vision/face";

/**
 * 미러필름에서 마지막 사진을 찍는 동안 카메라 영상을 셀카처럼 띄운다. 찍히는 범위 그대로 자르지 않는다.
 * children은 영상 위 가운데에 겹친다
 */
export function SelfiePreview({
  className,
  children,
}: {
  className?: string;
  children?: ReactNode;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const { videoRef } = useCamera();
  useFaceRender(() => {
    const c = canvas.current;
    const source = videoRef.current;
    if (!c || !source || source.readyState < 2 || !source.videoWidth) return;
    const ratio = window.devicePixelRatio || 1;
    const width = c.clientWidth;
    const height = c.clientHeight;
    const w = Math.round(width * ratio);
    const h = Math.round(height * ratio);
    if (c.width !== w || c.height !== h) {
      c.width = w;
      c.height = h;
    }
    const ctx = c.getContext("2d");
    if (!ctx) return;
    const scale = Math.min(width / source.videoWidth, height / source.videoHeight);
    const dw = source.videoWidth * scale;
    const dh = source.videoHeight * scale;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    // 화면에서 보던 방향(좌우 반전)으로 그린다
    ctx.translate((width + dw) / 2, (height - dh) / 2);
    ctx.scale(-1, 1);
    ctx.drawImage(source, 0, 0, dw, dh);
  });
  return (
    <div className={cn("relative overflow-hidden rounded-[24px] bg-black", className)}>
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      {children && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-night/20 text-center text-white">
          {children}
        </div>
      )}
    </div>
  );
}
