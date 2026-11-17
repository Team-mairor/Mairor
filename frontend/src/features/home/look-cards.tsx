/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */
import { Plus } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { isGuideId, type ReportSummary } from "@/domain/session";

/** 새 영상 고르기로 가는 큰 카드 */
export function NewLookCard() {
  return (
    <Link
      href="/select"
      className="flex min-w-0 flex-col justify-between rounded-3xl bg-navy p-6 hover:brightness-90"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="font-label text-[15px] font-semibold tracking-[.16em] text-blush">
          NEW LOOK
        </span>
        <span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-mint text-ink">
          <Plus className="size-[26px]" strokeWidth={1.8} aria-hidden />
        </span>
      </div>
      <div className="flex flex-col gap-3.5">
        <span className="font-display text-[28px] leading-[1.3] text-white">
          새 메이크업
          <br />
          영상 추가
        </span>
        <span className="self-start rounded-full bg-white px-[11px] py-1.5 text-[16px] font-semibold text-ink">
          YouTube 검색
        </span>
      </div>
    </Link>
  );
}

/** 가장 최근 리포트의 가이드를 다시 따라 하는 카드 */
export function AgainCard({ last, onReplay }: { last: ReportSummary; onReplay: () => void }) {
  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,.9fr)_minmax(0,1fr)] gap-[18px] rounded-3xl border border-line bg-white p-3.5">
      <div className="relative min-h-0 overflow-hidden rounded-2xl">
        <img
          src="/images/login-editorial.png"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[50%_32%]"
        />
      </div>
      <div className="flex min-w-0 flex-col justify-between py-2 pr-2">
        <div className="flex flex-col gap-2.5">
          <span className="flex items-baseline gap-2">
            <span className="font-serif text-[26px] leading-none text-ink italic">Again</span>
            <span className="text-[16px] text-mute">지난 가이드 다시 따라 하기</span>
          </span>
          <span className="font-display text-[21px] leading-[1.3] text-pretty text-ink">
            {last.title}
          </span>
        </div>
        <div className="flex flex-col gap-2.5">
          <span className="text-[15px] text-mute tabular">
            {last.date} 완료 · {last.steps}단계
          </span>
          <PillButton size="md" className="mt-1 h-12 text-[18px]" onClick={onReplay}>
            {isGuideId(last.guideId) ? "다시 하기" : "영상 다시 선택"}
          </PillButton>
        </div>
      </div>
    </div>
  );
}

/** 리포트를 받는 중이거나 받지 못했을 때 Again 자리에 띄우는 안내 */
export function NoteCard({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col justify-center rounded-3xl border border-line bg-white p-6">
      {children}
    </div>
  );
}

/** 완료한 리포트가 아직 없을 때 첫 시작을 권하는 카드 */
export function FirstLookCard() {
  return (
    <Link
      href="/select"
      className="flex min-w-0 flex-col justify-center gap-2.5 rounded-3xl border-[1.5px] border-dashed border-line-2 bg-white p-6 hover:border-navy"
    >
      <span className="font-serif text-[26px] leading-none text-navy italic">First look</span>
      <span className="font-display text-[22px] leading-[1.35] text-pretty text-ink">
        첫 메이크업을 시작해 보세요
      </span>
      <span className="text-[16px] leading-[1.5] text-pretty text-mute">
        영상을 골라 따라 하면 이곳에 다시 따라 할 수 있는 룩이 생겨요.
      </span>
    </Link>
  );
}
