import Link from "next/link";
import type { ReactNode } from "react";

import type { ReportSummary } from "@/domain/session";
import { EXAMPLE_LOOKS, ReportCard } from "@/features/report";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */

/** 홈 아래쪽 최근 리포트 3개. 받는 중·실패는 note로 알리고, 없으면 예시를 흐리게 보여 준다 */
export function RecentReports({
  reports,
  note,
}: {
  reports: ReportSummary[];
  /** 받는 중이거나 받지 못했을 때 보여 줄 안내. 없으면 목록을 보여 준다 */
  note: ReactNode | null;
}) {
  const shown = !note && reports.length === 0 ? EXAMPLE_LOOKS : null;
  return (
    <div data-tour="home-reports" className="flex shrink-0 flex-col gap-3">
      <div className="flex items-baseline justify-between gap-2.5">
        <span className="flex items-baseline gap-2.5">
          <span className="font-serif text-[34px] leading-none text-ink italic">Reports</span>
          <span className="text-[18px] text-mute">
            {shown ? "예시 · 완성하면 이렇게 쌓여요" : "최근 리포트"}
          </span>
        </span>
        <Link
          href={shown ? "/select" : "/my/reports"}
          className="text-[18px] font-semibold text-navy"
        >
          {shown ? "영상 고르기" : "전체 보기"}
        </Link>
      </div>
      {note ? (
        <div className="rounded-[22px] border border-line bg-white px-6 py-[22px]">{note}</div>
      ) : shown ? (
        // 리포트가 없으면 같은 자리에 예시 카드를 흐리게 보여 준다 (누를 수 없다)
        <div className="grid grid-cols-3 gap-3 opacity-40 grayscale mirror:opacity-70" inert>
          {shown.map((r) => (
            <div
              key={r.id}
              className="flex min-w-0 flex-col gap-2.5 rounded-[22px] border border-line bg-white px-2.5 pt-2.5 pb-3.5"
            >
              <span className="relative h-[110px] w-full shrink-0 overflow-hidden rounded-[14px]">
                <img
                  src={r.photoUrl}
                  alt=""
                  className={`absolute inset-0 h-full w-full object-cover ${r.photoClass}`}
                />
              </span>
              <span className="flex min-w-0 flex-col gap-1 px-1.5">
                <span className="truncate font-display text-[20px] leading-[1.3] text-ink">
                  {r.title}
                </span>
                <span className="text-[16px] text-mute">
                  {r.date} · {r.steps}단계
                </span>
              </span>
            </div>
          ))}
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
