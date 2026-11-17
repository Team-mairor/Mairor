/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */
import Link from "next/link";

import type { ReportSummary } from "@/domain/session";

import { PhotoSlot } from "./done-view";

/**
 * 리포트 카드. 홈의 최근 리포트는 작은 카드(compact)로, 리포트 목록의 지난 룩은
 * 살짝 기울인 사진 카드(polaroid)로 보여 준다. 누르면 그 리포트를 연다
 */
export function ReportCard({
  report: r,
  variant,
  rotate = 0,
}: {
  report: ReportSummary;
  variant: "compact" | "polaroid";
  /** polaroid에서 카드를 기울이는 각도(deg) */
  rotate?: number;
}) {
  const href = `/my/report?id=${r.id}`;

  if (variant === "compact") {
    return (
      <Link
        href={href}
        className="flex min-w-0 flex-col gap-2.5 rounded-[22px] border border-line bg-white px-2.5 pt-2.5 pb-3.5 hover:border-navy"
      >
        <span className="relative h-[110px] w-full shrink-0 overflow-hidden rounded-[14px]">
          {r.photoUrl ? (
            <img src={r.photoUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center bg-cream text-[14px] font-bold text-mute">
              사진 없음
            </div>
          )}
        </span>
        <span className="flex min-w-0 flex-col gap-1 px-1.5">
          <span className="truncate font-display text-[20px] leading-[1.3] text-ink">
            {r.title}
          </span>
          <span className="text-[16px] text-mute">
            {r.date} · {r.steps}단계
          </span>
        </span>
      </Link>
    );
  }

  return (
    <Link
      href={href}
      className="flex min-w-0 flex-col gap-3.5 rounded-[10px] bg-white px-3 pt-3 pb-[18px] shadow-float ring-1 ring-line transition-transform hover:translate-y-[-4px] hover:rotate-0"
      style={{ transform: `rotate(${rotate}deg)` }}
    >
      <div className="relative aspect-[4/5] overflow-hidden rounded bg-cream">
        {r.photoUrl ? (
          <img src={r.photoUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
        ) : r.noPhoto || r.finalPhoto === false ? (
          <div className="absolute inset-0 flex items-center justify-center text-[16px] font-bold text-mute">
            미촬영
          </div>
        ) : r.guide ? (
          <PhotoSlot label="마지막 단계 사진" />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-[16px] font-bold text-mute">
            사진 없음
          </div>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-1 px-1.5">
        <span className="truncate font-display text-[22px] leading-[1.25] text-ink">{r.title}</span>
        <span className="text-[15px] text-mute">
          {r.date} · {r.steps} STEP
        </span>
      </div>
    </Link>
  );
}
