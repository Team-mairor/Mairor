import { cn } from "@/lib/utils";

/** 영상에서 찾은 제품 칸. 보유는 네이비, 없는 제품은 탭해서 파우치에 추가한다 */
export function FoundProducts({
  rows,
  foundCount,
  haveCount,
  onAdd,
}: {
  rows: { id: string; cat: string; color: string; found: boolean; next: boolean; have: boolean }[];
  foundCount: number;
  haveCount: number;
  onAdd: () => void;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex min-w-0 items-baseline gap-2.5">
          <span className="font-serif text-[32px] leading-none whitespace-nowrap text-ink italic">
            Found in video
          </span>
          <span className="truncate text-[19px] text-mute">없는 제품은 탭해서 파우치에 추가</span>
        </span>
        <span className="text-[19px] whitespace-nowrap text-mute tabular">
          {foundCount} / {rows.length} · 파우치 {haveCount}
        </span>
      </div>
      {/* 단계 수는 영상마다 달라, 두 줄을 넘으면 이 안에서 넘겨 본다 */}
      <div className="grid max-h-[168px] grid-cols-4 gap-2 overflow-y-auto">
        {rows.length === 0 && (
          <span className="col-span-4 py-5 text-[19px] text-mute">아직 찾은 제품이 없어요</span>
        )}
        {rows.map((r) =>
          r.found ? (
            <button
              key={r.id}
              type="button"
              disabled={r.have}
              onClick={onAdd}
              className={cn(
                "flex h-20 items-center gap-3 rounded-[20px] border px-4 text-left transition-colors",
                r.have ? "border-navy bg-navy" : "border-line bg-white",
              )}
              style={{ animation: "mr-fade 600ms cubic-bezier(.34,1.56,.64,1) both" }}
            >
              <span
                className="size-[34px] shrink-0 rounded-full border-2 border-white ring-1 ring-line"
                style={{ background: r.color }}
              />
              <span className="flex min-w-0 flex-col gap-0.5 overflow-hidden">
                <span
                  className={cn(
                    "truncate text-[21px] font-semibold",
                    r.have ? "text-white" : "text-mute",
                  )}
                >
                  {r.cat}
                </span>
                <span className={cn("truncate text-[18px]", r.have ? "text-blush" : "text-mute")}>
                  {r.have ? "보유" : "없음 · 추가"}
                </span>
              </span>
            </button>
          ) : (
            <div
              key={r.id}
              className="flex h-20 items-center gap-3 rounded-[20px] border border-dashed border-line-3 px-4 text-[19px] text-mute"
            >
              <span className="size-[34px] shrink-0 rounded-full bg-cream" />
              {r.next ? "찾는 중…" : "대기"}
            </div>
          ),
        )}
      </div>
    </div>
  );
}
