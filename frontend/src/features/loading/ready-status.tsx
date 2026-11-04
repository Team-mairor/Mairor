import { cn } from "@/lib/utils";

/** 하단 준비 상태 두 칸 (가이드·얼굴 인식) */
export function ReadyStatus({ items }: { items: [label: string, state: string, ok: boolean][] }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map(([label, st, ok]) => (
        <div
          key={label}
          className="flex h-[68px] min-w-0 items-center gap-3 rounded-[20px] border border-line px-5"
        >
          <span className={cn("size-3 shrink-0 rounded-full", ok ? "bg-cyan" : "bg-line-3")} />
          <span className="text-[21px] font-semibold whitespace-nowrap text-ink">{label}</span>
          <span
            className={cn(
              "ml-auto text-[20px] font-semibold whitespace-nowrap tabular",
              ok ? "text-navy" : "text-mute",
            )}
          >
            {st}
          </span>
        </div>
      ))}
    </div>
  );
}
