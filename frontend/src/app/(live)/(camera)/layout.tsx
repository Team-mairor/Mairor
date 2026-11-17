import { FaceStateProvider } from "@/features/live";
import { StartCamera } from "@/vision/face";

// 카메라는 상위 (live) 레이아웃이 한 번만 켜서, 로딩에서 얼굴을 등록했으면 그대로 이어 쓴다.
// 제품 체크 → 튜토리얼은 얼굴 화면을 유지하고 하단 UI만 바뀐다 (연속 화면).
// 각 화면은 LiveNote 또는 CameraErrorNote로 카메라 오류를 직접 보여 준다.
export default function CameraLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <StartCamera />
      <FaceStateProvider>{children}</FaceStateProvider>
    </>
  );
}
