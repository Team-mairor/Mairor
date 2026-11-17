import { Check } from "lucide-react";

/** 키워드 칩·채널 동그라미 배경 (돌아가며 쓴다) */
export const KW_BG = ["bg-blush", "bg-mint", "bg-sky"];

export function GuideBadge() {
  return (
    <span className="mt-1 flex h-7 items-center gap-1.5 self-start rounded-full bg-mint px-2.5 text-[14px] font-bold text-ink">
      <Check className="size-3" strokeWidth={3} aria-hidden />
      가이드 있음 · 바로 따라 하기
    </span>
  );
}
