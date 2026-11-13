"use client";

import { X } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * 튜토리얼 상단: 나가기·부위 묶음 진행바. 준비 카드(z-[4]) 위에 둬서 카드가 떠 있어도 누를 수 있다.
 * 칸 하나가 연속한 같은 부위 단계 묶음이다.
 */
export function TutorialTopBar({
  groups,
  group,
  reachable,
  onExit,
  onGoGroup,
}: {
  groups: readonly { label: string }[];
  group: number;
  /** 눌러서 갈 수 있는 마지막 묶음. 앞 묶음 사진이 모두 있어야 그 뒤로 갈 수 있다 */
  reachable: number;
  onExit: () => void;
  onGoGroup: (i: number) => void;
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
      <div className="flex h-12 min-w-0 flex-1 items-center gap-3.5 rounded-full border border-white/15 bg-night/80 px-[18px]">
        <div
          className="flex min-w-0 flex-1 gap-1"
          role="progressbar"
          aria-valuenow={group + 1}
          aria-valuemax={groups.length}
        >
          {groups.map((g, i) => (
            <button
              key={i}
              type="button"
              onClick={() => onGoGroup(i)}
              disabled={i > reachable}
              aria-label={`${i + 1}단계 ${g.label}`}
              className={cn(
                "h-1.5 flex-1 rounded-full transition-colors",
                i < group ? "bg-navy" : i === group ? "bg-ice" : "bg-line-2",
              )}
            />
          ))}
        </div>
        <span className="font-serif text-[24px] leading-none whitespace-nowrap text-white tabular">
          {group + 1} / {groups.length}
        </span>
      </div>
    </div>
  );
}
