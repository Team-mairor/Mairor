// 카메라·얼굴 추적은 여기서 한 번만 시작해 페이지 이동 시 다시 초기화하지 않는다.
export default function CameraLayout({ children }: LayoutProps<"/">) {
  return <div className="relative flex flex-1 flex-col">{children}</div>;
}
