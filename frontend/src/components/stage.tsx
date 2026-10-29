import type { CSSProperties, ReactNode } from "react";

import { cn } from "@/lib/utils";

/** 프로토타입 기준 화면 크기. 세로 거울 화면(3:5) */
export const STAGE = { width: 800, height: 1333 } as const;

/**
 * 좌표가 고정된 연출(인트로)을 화면에 맞춰 통째로 축소·확대한다.
 * tan(atan2())로 길이 비율을 숫자로 바꿔 CSS만으로 scale을 구한다.
 */
export function Stage({ children, className }: { children: ReactNode; className?: string }) {
  const style = {
    width: STAGE.width,
    height: STAGE.height,
    scale: `min(tan(atan2(100dvw, ${STAGE.width}px)), tan(atan2(100dvh, ${STAGE.height}px)))`,
  } as CSSProperties;
  return (
    <div className="flex flex-1 items-center justify-center overflow-hidden">
      <div
        className={cn("relative shrink-0 origin-center overflow-hidden bg-white", className)}
        style={style}
      >
        {children}
      </div>
    </div>
  );
}
