/** 모달 상단 진행 바. 왼쪽 글씨와 오른쪽 퍼센트, 아래 채워지는 선 */
export function ProgressBar({ pct, text }: { pct: number; text: string }) {
  return (
    <div className="relative flex h-[60px] shrink-0 items-center gap-3 bg-cream px-8">
      <span
        className="absolute bottom-0 left-0 h-[3px] bg-cyan transition-[width] duration-600 ease-linear"
        style={{ width: `${pct}%` }}
      />
      <span className="size-2 shrink-0 rounded-full bg-cyan" />
      <span className="text-[17px] font-semibold text-ink">{text}</span>
      <span className="ml-auto font-serif text-[26px] leading-none text-navy tabular">{pct}%</span>
    </div>
  );
}
