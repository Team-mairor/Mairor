import { ArrowRight } from "lucide-react";

/** 영상 속 제품 → 내 제품 한 줄. 자세한 건 준비 카드에 있다 */
export function ProductChip({
  refProduct,
  mine,
}: {
  refProduct: { name: string; color: string };
  /** 이 단계에 쓸 내 제품. 없으면 '내 파우치에 없음' */
  mine: { name: string; color?: string | null } | null;
}) {
  return (
    <div className="absolute top-[84px] left-5 z-[2] flex h-11 max-w-[calc(100%-40px)] items-center gap-2 rounded-full bg-white/92 py-0 pr-4 pl-2 text-[14px] font-bold text-ink backdrop-blur-md">
      <span
        className="size-7 shrink-0 rounded-full border-2 border-white ring-1 ring-line"
        style={{ background: refProduct.color }}
        aria-label="영상 속 제품 색"
      />
      <span className="max-w-[200px] truncate text-mute">{refProduct.name}</span>
      <ArrowRight className="size-4 shrink-0 text-navy" strokeWidth={2.4} aria-hidden />
      {mine ? (
        <>
          <span
            className="size-7 shrink-0 rounded-full border-2 border-white ring-1 ring-line"
            style={{ background: mine.color ?? "#fff" }}
            aria-label="내 제품 색"
          />
          <span className="max-w-[200px] truncate">{mine.name}</span>
        </>
      ) : (
        <span className="whitespace-nowrap text-navy">내 파우치에 없음</span>
      )}
    </div>
  );
}
