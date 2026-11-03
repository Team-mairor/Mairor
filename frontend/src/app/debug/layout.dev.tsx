import type { ReactNode } from "react";

/**
 * 확인 화면(face · overlay · preview · tutorial) 묶음.
 * data-debug 아래에서는 앱 화면용 800px 칸·폭 축소·브랜드 색을 끄고 원래 shadcn 기본 스타일로 보인다 (globals.css).
 */
export default function DebugLayout({ children }: { children: ReactNode }) {
  return (
    <div data-debug className="contents">
      {children}
    </div>
  );
}
