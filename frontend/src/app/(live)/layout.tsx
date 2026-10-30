import { CameraProvider } from "@/features/face";

// 얼굴 등록(로딩) → 미리보기 → 제품 체크 → 튜토리얼이 카메라·얼굴 추적을 한 번만 켜서 함께 쓴다.
// 로딩 화면은 얼굴 등록을 시작할 때, 카메라 화면은 들어올 때 켠다(StartCamera). 이 묶음을 떠나면 끈다.
// errorView="none"이라 각 화면이 카메라 오류를 직접 보여 준다.
export default function LiveLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative flex min-h-dvh flex-1 flex-col bg-ink-deep text-white">
      <CameraProvider autoStart={false} errorView="none">
        {children}
      </CameraProvider>
    </div>
  );
}
