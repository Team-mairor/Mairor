import { CameraProvider } from "@/features/face";
import { FaceStateProvider } from "@/features/live/live-chrome";

// 카메라·얼굴 추적은 여기서 한 번만 시작해 페이지 이동 시 다시 초기화하지 않는다.
// 미리보기 → 제품 체크 → 튜토리얼은 얼굴 화면을 유지하고 하단 UI만 바뀐다 (연속 화면).
// errorView="none"이라 각 화면이 LiveNote 또는 CameraErrorNote로 카메라 오류를 직접 보여 준다.
export default function CameraLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative flex min-h-dvh flex-1 flex-col bg-ink-deep text-white">
      <CameraProvider errorView="none">
        <FaceStateProvider>{children}</FaceStateProvider>
      </CameraProvider>
    </div>
  );
}
