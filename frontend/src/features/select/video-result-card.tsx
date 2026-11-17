import { toVideoItem, videoThumb, type VideoItem } from "@/domain/video";
import type { VideoSearchItem } from "@/lib/api";
import { cn } from "@/lib/utils";

import { GuideBadge, KW_BG } from "./video-parts";

/** 검색 결과 한 줄. 썸네일과 채널·제목을 보여 주고 누르면 영상을 고른다 */
export function VideoResultCard({
  item,
  index,
  onPick,
}: {
  item: VideoSearchItem;
  /** 채널 동그라미 색을 돌려 쓰는 순번 */
  index: number;
  onPick: (video: VideoItem) => void;
}) {
  const v = toVideoItem(item);
  return (
    <button type="button" onClick={() => onPick(v)} className="flex flex-col gap-3 text-left">
      <div
        className="relative aspect-video bg-cream bg-cover bg-center"
        style={{ backgroundImage: `url(${videoThumb(v.ytid)})` }}
      >
        <span
          data-dark
          className="absolute right-2.5 bottom-2.5 rounded bg-black/80 px-[5px] py-0.5 text-[16px] font-semibold text-white tabular"
        >
          {v.dur}
        </span>
      </div>
      <div className="flex items-start gap-3 px-5">
        <span
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-full text-[18px] font-bold text-ink",
            KW_BG[index % 3],
          )}
        >
          {v.ch.slice(-1)}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-[19px] leading-[1.35] font-semibold text-ink">{v.title}</span>
          <span className="text-[16px] text-mute">
            {v.ch} · {v.meta}
          </span>
          {item.guideAvailable && <GuideBadge />}
        </span>
      </div>
    </button>
  );
}
