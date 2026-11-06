import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** 레이아웃 기준 크기(globals.css의 800×1200). 시연 기기 S6 키오스크(800×1280)에서는 위아래 40px 여백으로 가운데 놓인다 */
export const STAGE = { width: 800, height: 1200 } as const;

/**
 * 좌표가 고정된 연출(인트로)을 앱 화면 크기 그대로 가운데에 놓는다.
 * 앱 전체가 html zoom으로 800×1200을 창에 맞춰 줄이므로 여기서 따로 배율을 구하지 않는다.
 * 예전에는 창(dvw·dvh) 기준으로 한 번 더 줄여서 인트로가 작게 보였다.
 */
export function Stage({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className="flex flex-1 items-center justify-center overflow-hidden">
      <div
        className={cn("relative shrink-0 overflow-hidden bg-white", className)}
        style={{ width: STAGE.width, height: STAGE.height }}
      >
        {children}
      </div>
    </div>
  );
}
