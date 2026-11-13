import { BottomTabs } from "@/components/bottom-tabs";

/**
 * 하단 탭이 있는 화면 묶음: 홈 · 촬영 · 영상 입력 · 마이페이지 · 리포트 상세. 뒤로·홈 버튼 없이 탭으로 옮겨 다닌다
 * 높이를 화면에 고정하고 본문만 스크롤해, 내용 길이와 상관없이 탭이 늘 같은 자리에 있게 한다
 * 높이는 globals.css의 --screen-h를 쓴다
 */
export default function TabsLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative flex h-(--screen-h) flex-col">
      <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</div>
      <BottomTabs />
    </div>
  );
}
