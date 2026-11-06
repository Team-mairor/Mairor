import type { ReactNode } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { CameraProvider } from "@/features/face";

// 카메라·얼굴 추적은 여기서 한 번만 시작해 페이지 이동 시 다시 초기화하지 않는다.
export default function CameraLayout({ children }: { children: ReactNode }) {
  return (
    <CameraProvider>
      <header className="relative z-10 flex flex-wrap items-center gap-3 bg-background p-3">
        <MirrorToggle />
        <span className="text-sm">
          끄면 카메라 영상 · 켜면 미러필름용 화면 (카메라 추적은 유지)
        </span>
      </header>
      {children}
    </CameraProvider>
  );
}
