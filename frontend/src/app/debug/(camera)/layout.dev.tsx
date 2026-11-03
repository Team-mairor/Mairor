import type { ReactNode } from "react";

import { CameraProvider } from "@/features/face";

// 카메라·얼굴 추적은 여기서 한 번만 시작해 페이지 이동 시 다시 초기화하지 않는다.
export default function CameraLayout({ children }: { children: ReactNode }) {
  return <CameraProvider>{children}</CameraProvider>;
}
