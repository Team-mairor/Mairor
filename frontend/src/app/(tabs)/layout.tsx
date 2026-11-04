import { BottomTabs } from "@/components/bottom-tabs";

/**
 * 하단 탭이 있는 화면 묶음: 홈 · 마이페이지 · 리포트 상세
 * 높이를 화면에 고정하고 본문만 스크롤해, 내용 길이와 상관없이 탭이 늘 같은 자리에 있게 한다
 * dvh도 html zoom만큼 줄어들기 때문에 zoom으로 나눠 실제 화면 높이에 맞춘다
 */
export default function TabsLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="relative flex h-[calc(100dvh/var(--zoom))] flex-col">
      <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</div>
      <BottomTabs />
    </div>
  );
}
