import { BottomTabs } from "@/components/bottom-tabs";

/** 하단 탭이 있는 화면 묶음: 홈 · 마이페이지 · 리포트 상세 */
export default function TabsLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative flex min-h-dvh flex-1 flex-col">
      <div className="relative flex min-h-0 flex-1 flex-col">{children}</div>
      <BottomTabs />
    </div>
  );
}
