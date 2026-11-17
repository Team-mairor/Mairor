import { Trophy } from "lucide-react";

import { toVideoItem, videoThumb } from "@/domain/video";
import type { PopularVideoItem } from "@/lib/api";
import { cn } from "@/lib/utils";

import { GuideBadge } from "./video-parts";

/** 인기 Top 4 한 칸. 순위와 영상 정보를 보여 주고 누르면 바로 시작한다 */
export function PopularVideoCard({
  item,
  busy,
  onPick,
}: {
  item: PopularVideoItem;
  busy: boolean;
  onPick: () => void;
}) {
  const v = toVideoItem(item);
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onPick}
      className="flex flex-col gap-2.5 rounded-[20px] border-2 border-transparent p-2 text-left hover:border-line disabled:opacity-60"
    >
      <div
        className="relative aspect-video overflow-hidden rounded-[14px] border border-line bg-cover bg-center"
        style={{ backgroundImage: `url(${videoThumb(v.ytid)})` }}
      >
        <span className="absolute right-2 bottom-2 rounded-md bg-ink px-2.5 py-1 text-[16px] font-semibold text-white tabular">
          {v.dur}
        </span>
        <span
          className={cn(
            "absolute top-2 left-2 flex h-9 items-center gap-1.5 rounded-full py-0 pr-3.5 pl-2.5 text-[16px] font-bold tabular",
            item.rank === 1 ? "bg-mint text-ink" : "bg-ink text-white",
          )}
        >
          <Trophy className="size-[18px]" aria-hidden />
          {item.rank}위
        </span>
      </div>
      <span className="flex flex-col gap-1 px-1 pb-1">
        <span className="font-display text-[17px] leading-[1.3] text-ink">{v.title}</span>
        <span className="text-[16px] text-mute">{v.ch}</span>
        {item.guideAvailable && <GuideBadge />}
      </span>
    </button>
  );
}
