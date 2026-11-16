"use client";

import { List, X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * 튜토리얼 상단: 나가기·단계 진행바. 준비 카드(z-[4]) 위에 둬서 카드가 떠 있어도 누를 수 있다.
 * 칸 하나가 연속한 같은 제품 단계 묶음이다. 진행바를 누르면 단계 목록을 연다.
 */
export function TutorialTopBar({
  groups,
  group,
  listDisabled,
  onExit,
  onList,
}: {
  groups: readonly { label: string }[];
  group: number;
  /** 사진을 저장하는 동안은 목록을 열지 않는다 */
  listDisabled: boolean;
  onExit: () => void;
  onList: () => void;
}) {
  return (
    <div className="absolute inset-x-5 top-5 z-[5] flex items-center gap-3.5">
      <button
        type="button"
        onClick={onExit}
        className="flex h-12 shrink-0 items-center gap-2 rounded-full border border-white/15 bg-night/80 py-0 pr-[18px] pl-3 text-[16px] font-bold whitespace-nowrap text-white hover:bg-night/95"
      >
        <X className="size-[18px]" strokeWidth={2.4} aria-hidden />
        나가기
      </button>
      <button
        type="button"
        onClick={onList}
        disabled={listDisabled}
        aria-label="단계 목록 열기"
        className="flex h-12 min-w-0 flex-1 items-center gap-3.5 rounded-full border border-white/15 bg-night/80 px-[18px] hover:bg-night/95 disabled:opacity-60"
      >
        <span
          className="flex min-w-0 flex-1 gap-1"
          role="progressbar"
          aria-valuenow={group + 1}
          aria-valuemax={groups.length}
        >
          {groups.map((g, i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 flex-1 rounded-full transition-colors",
                i < group ? "bg-navy" : i === group ? "bg-ice" : "bg-line-2",
              )}
            />
          ))}
        </span>
        <span className="font-serif text-[24px] leading-none whitespace-nowrap text-white tabular">
          {group + 1} / {groups.length}
        </span>
        <List className="size-[22px] shrink-0 text-white" strokeWidth={2.2} aria-hidden />
      </button>
    </div>
  );
}
