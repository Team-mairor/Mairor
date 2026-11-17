import { Check } from "lucide-react";

import { GROUPS, TAG_BG } from "@/domain/check";
import type { MatchKind } from "@/domain/session";
import { cn } from "@/lib/utils";

function GroupTab({
  group: { k, label, dot },
  on,
  count,
  onClick,
}: {
  group: (typeof GROUPS)[number];
  on: boolean;
  count: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={on}
      onClick={onClick}
      className={cn(
        "flex h-[76px] items-center gap-3 rounded-[20px] px-5 transition-[background,box-shadow]",
        on ? cn(TAG_BG[k], "shadow-float") : "hover:bg-white/8",
      )}
    >
      {on ? (
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-ink text-[#fff]">
          <Check className="size-4" strokeWidth={3.2} aria-hidden />
        </span>
      ) : (
        <span className="size-3.5 shrink-0 rounded-full" style={{ background: dot }} />
      )}
      <span
        className={cn(
          "min-w-0 flex-1 text-left text-[24px] font-extrabold",
          on ? "text-ink" : "text-white",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "font-serif text-[48px] leading-none tabular",
          on ? "text-ink" : "text-line-2",
        )}
      >
        {count}
      </span>
    </button>
  );
}

/** 보유·대체·없음 탭. 단계 수를 함께 보여 준다 */
export function GroupTabs({
  active,
  counts,
  onChange,
}: {
  active: MatchKind;
  counts: Record<MatchKind, number>;
  onChange: (k: MatchKind) => void;
}) {
  return (
    <div
      className="mx-8 grid grid-cols-3 gap-1.5 rounded-[26px] border border-white/12 bg-white/8 p-1.5"
      role="tablist"
    >
      {GROUPS.map((g) => (
        <GroupTab
          key={g.k}
          group={g}
          on={active === g.k}
          count={counts[g.k]}
          onClick={() => onChange(g.k)}
        />
      ))}
    </div>
  );
}
