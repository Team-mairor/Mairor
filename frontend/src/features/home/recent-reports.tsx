import Link from "next/link";
import type { ReactNode } from "react";

import type { ReportSummary } from "@/domain/session";
import { ReportCard } from "@/features/report";

/** 홈 아래쪽 최근 리포트 3개. 받는 중·실패는 note로 알리고, 없으면 시작을 권한다 */
export function RecentReports({
  reports,
  note,
}: {
  reports: ReportSummary[];
  /** 받는 중이거나 받지 못했을 때 보여 줄 안내. 없으면 목록을 보여 준다 */
  note: ReactNode | null;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-3">
      <div className="flex items-baseline justify-between gap-2.5">
        <span className="flex items-baseline gap-2.5">
          <span className="font-serif text-[34px] leading-none text-ink italic">Reports</span>
          <span className="text-[18px] text-mute">최근 리포트</span>
        </span>
        <Link href="/my/reports" className="text-[18px] font-semibold text-navy">
          전체 보기
        </Link>
      </div>
      {note ? (
        <div className="rounded-[22px] border border-line bg-white px-6 py-[22px]">{note}</div>
      ) : reports.length === 0 ? (
        <div className="flex items-center justify-between gap-4 rounded-[22px] border border-line bg-white px-6 py-[22px]">
          <span className="text-[17px] leading-[1.5] text-pretty text-mute">
            아직 완료한 메이크업이 없어요. 영상을 골라 따라 해 보세요.
          </span>
          <Link href="/select" className="shrink-0 text-[17px] font-bold text-navy">
            영상 고르기
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {reports.slice(0, 3).map((r) => (
            <ReportCard key={r.id} report={r} variant="compact" />
          ))}
        </div>
      )}
    </div>
  );
}
