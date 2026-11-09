"use client";

import { videoThumb } from "@/features/video";

const TAG_POS: [number, number][] = [
  [50, 60],
  [34, 45],
  [30, 28],
  [66, 28],
  [20, 62],
  [66, 50],
  [50, 80],
];

/**
 * 영상 썸네일 위 스캔 연출. 찾은 제품 이름표를 썸네일 위에 띄운다.
 * 사진 위라 미러필름 모드에서도 흰 선·점은 흰색 그대로 둔다(data-dark)
 */
export function ScanPreview({
  ytid,
  title,
  status,
  running,
  pct,
  rows,
  foundCount,
}: {
  /** 모르면 null. 썸네일 없이 어두운 바탕만 보여 준다 */
  ytid: string | null;
  title: string;
  /** 왼쪽 아래 상태 글씨 */
  status: string;
  /** 분석 중이면 스캔 선을 움직인다 */
  running: boolean;
  pct: number;
  rows: { id: string; cat: string; found: boolean }[];
  foundCount: number;
}) {
  return (
    <div
      data-dark
      className="relative aspect-video w-full shrink-0 overflow-hidden rounded-3xl bg-ink"
    >
      {ytid && (
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url(${videoThumb(ytid)})` }}
        />
      )}
      <div className="absolute inset-0 bg-night/20" />
      <div className="absolute inset-7">
        <span className="absolute top-0 left-0 size-[34px] rounded-tl-[10px] border-t-2 border-l-2 border-white" />
        <span className="absolute top-0 right-0 size-[34px] rounded-tr-[10px] border-t-2 border-r-2 border-white" />
        <span className="absolute bottom-0 left-0 size-[34px] rounded-bl-[10px] border-b-2 border-l-2 border-white" />
        <span className="absolute right-0 bottom-0 size-[34px] rounded-br-[10px] border-r-2 border-b-2 border-white" />
      </div>
      {running && (
        <div
          data-dark
          className="absolute inset-x-7 h-[1.5px] bg-white shadow-[0_0_16px_3px_rgba(255,255,255,.55)]"
          style={{ top: `${10 + ((pct * 9) % 100) * 0.8}%` }}
        />
      )}
      {/* 자리가 TAG_POS만큼이라, 단계가 많으면 가장 최근에 찾은 것만 남겨 겹치지 않게 한다 */}
      {rows.map((r, i) =>
        r.found && i >= foundCount - TAG_POS.length ? (
          <div
            key={r.id}
            className="absolute flex items-center gap-2"
            style={{
              left: `${TAG_POS[i % TAG_POS.length][0]}%`,
              top: `${TAG_POS[i % TAG_POS.length][1]}%`,
              animation: "mr-fade 600ms cubic-bezier(.34,1.56,.64,1) both",
            }}
          >
            <span
              data-dark
              className="size-2.5 rounded-full bg-white"
              style={{ animation: "mr-pulse 1.6s ease-out infinite" }}
            />
            <span className="rounded-full bg-white/90 px-2.5 py-1 text-[12px] font-semibold whitespace-nowrap text-ink">
              {r.cat}
            </span>
          </div>
        ) : null,
      )}
      <span className="absolute bottom-[18px] left-5 rounded-full bg-white px-3 py-[7px] font-label text-[11px] font-semibold tracking-[.14em] text-ink">
        {status}
      </span>
      <span className="absolute right-5 bottom-[18px] max-w-[55%] truncate text-[13px] font-semibold text-white">
        {title}
      </span>
    </div>
  );
}
