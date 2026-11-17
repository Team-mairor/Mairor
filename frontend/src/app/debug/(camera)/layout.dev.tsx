import type { ReactNode } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { CameraProvider } from "@/vision/face";

// 카메라·얼굴 추적은 여기서 한 번만 시작해 페이지 이동 시 다시 초기화하지 않는다.
export default function CameraLayout({ children }: { children: ReactNode }) {
  return (
    <CameraProvider>
      <header className="relative z-10 flex shrink-0 items-center bg-background px-3 pt-2">
        <MirrorToggle />
      </header>
      {children}
    </CameraProvider>
  );
}
