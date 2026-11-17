import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

/** 제품의 컬러(호수) 한 줄. 고른 컬러는 굵게 표시한다 */
export function ShadeOption({
  name,
  hex,
  selected,
  onPick,
}: {
  name: string;
  /** 대표 색. 없으면 빈 칸 색 */
  hex: string | null;
  selected: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      className={cn(
        "flex min-h-[60px] items-center gap-3.5 pr-[18px] pl-4 text-left hover:bg-ice-pale",
        selected && "bg-ice-pale",
      )}
    >
      <span
        className="size-8 shrink-0 rounded-full"
        style={{
          background: hex ?? "var(--color-cream)",
          boxShadow: "inset 0 0 0 1px rgba(0,0,0,.15)",
        }}
      />
      <span
        className={cn(
          "min-w-0 flex-1 text-[19px] text-ink",
          selected ? "font-bold" : "font-semibold",
        )}
      >
        {name}
      </span>
      {selected && <Check className="size-[22px] text-navy" strokeWidth={2.6} aria-hidden />}
    </button>
  );
}
