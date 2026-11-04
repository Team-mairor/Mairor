"use client";

import { Check, ChevronLeft, Lock, Play, Search, X } from "lucide-react";
import { useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { PillButton } from "@/components/ui/pill-button";
import { videoThumb, type Chapter, type VideoItem, type VideoState } from "@/features/video";
import { cn } from "@/lib/utils";

/** 키워드 칩·채널 동그라미 배경 (돌아가며 쓴다) */
export const KW_BG = ["bg-blush", "bg-mint", "bg-sky"];

/**
 * 앱 안에서 여는 YouTube 검색 화면. 검색 → 영상 미리보기(재생·챕터) → 고르기.
 * 열 때마다 새로 그리므로 검색어·선택 영상은 여기서만 들고 있다
 */
export function VideoPicker({
  initialQuery,
  videos,
  stateOf,
  chapters,
  apiFail,
  onRetry,
  onClose,
  onPick,
}: {
  initialQuery: string;
  videos: VideoItem[];
  /** 영상마다 가이드 있음·재생 불가 등 상태. API가 붙기 전에는 화면이 샘플 분기를 넘긴다 */
  stateOf: (video: VideoItem | null) => VideoState;
  chapters: Chapter[];
  /** 검색 실패 상태 */
  apiFail: boolean;
  onRetry: () => void;
  onClose: () => void;
  onPick: (video: VideoItem) => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [sel, setSel] = useState<VideoItem | null>(null);
  const [playing, setPlaying] = useState(false);

  const q = query.trim();
  const results = videos.filter((v) => !q || v.title.includes(q) || v.ch.includes(q));
  const list = results.length ? results : videos;
  const selState = stateOf(sel);

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white">
      <div className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton size={44} icon="close" onClick={onClose} title="닫기" aria-label="닫기" />
        <span className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-full bg-cream px-4">
          <Lock className="size-3.5 text-mute" strokeWidth={2} aria-hidden />
          <span className="truncate text-[17px] text-ink">
            YouTube 검색{q ? ` · "${q}"` : " · 메이크업"}
          </span>
        </span>
        <span className="text-[16px] font-semibold whitespace-nowrap text-mute">
          mairor 안에서 열림
        </span>
      </div>
      {!sel && (
        <div className="shrink-0 px-7 pt-4">
          <label className="flex h-[52px] items-center gap-2.5 rounded-full border border-line px-[18px]">
            <Search className="size-[18px] text-mute" strokeWidth={1.8} aria-hidden />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="메이크업 영상 검색"
              className="min-w-0 flex-1 bg-transparent text-[19px] text-ink outline-none"
              autoFocus
            />
          </label>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto pt-4">
        {sel ? (
          <div className="flex flex-col">
            <button
              type="button"
              onClick={() => setSel(null)}
              className="flex items-center gap-2 px-8 pb-3 text-left text-[17px] font-semibold text-navy"
            >
              <ChevronLeft className="size-4" strokeWidth={2} aria-hidden />
              검색 결과로
            </button>
            <div className="relative aspect-video bg-black">
              {selState === "blocked" && (
                <div
                  data-dark
                  className="absolute inset-0 z-[2] flex flex-col items-center justify-center gap-2.5 bg-night/80 p-6 text-center text-white"
                >
                  <span className="text-[21px] font-bold">
                    이 영상은 mairor에서 재생할 수 없어요
                  </span>
                  <span className="text-[16px] leading-[1.5] text-line-2">
                    업로더가 외부 재생을 막았거나 비공개·삭제된 영상이에요. 다른 영상을 골라 주세요.
                  </span>
                </div>
              )}
              {playing ? (
                <iframe
                  src={`https://www.youtube.com/embed/${sel.ytid}?rel=0&playsinline=1&autoplay=1`}
                  title="YouTube video"
                  referrerPolicy="strict-origin-when-cross-origin"
                  className="block h-full w-full border-0"
                  allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setPlaying(true)}
                  className="absolute inset-0 flex items-center justify-center bg-cover bg-center"
                  style={{ backgroundImage: `url(${videoThumb(sel.ytid)})` }}
                  aria-label="재생"
                >
                  <span className="flex size-[84px] items-center justify-center rounded-full bg-white shadow-[0_10px_30px_rgba(0,0,0,.25)]">
                    <Play className="size-[30px] fill-navy text-navy" aria-hidden />
                  </span>
                  <span
                    data-dark
                    className="absolute right-3 bottom-3 rounded bg-black/80 px-2.5 py-1 text-[16px] font-semibold text-white"
                  >
                    {sel.dur}
                  </span>
                </button>
              )}
            </div>
            <div className="flex flex-col gap-3.5 px-10 pt-5 pb-2">
              <span className="text-[21px] leading-[1.35] font-semibold text-ink">{sel.title}</span>
              <div className="flex items-center gap-3">
                <span className="flex size-10 items-center justify-center rounded-full bg-blush text-[18px] font-bold text-ink">
                  {sel.ch.slice(-1)}
                </span>
                <span className="flex flex-col gap-0.5">
                  <span className="text-[18px] font-semibold text-ink">{sel.ch}</span>
                  <span className="text-[16px] text-mute">{sel.meta}</span>
                </span>
                <a
                  href={`https://www.youtube.com/watch?v=${sel.ytid}`}
                  target="_blank"
                  rel="noopener"
                  className="ml-auto text-[16px] font-semibold text-navy"
                >
                  YouTube에서 보기 ↗
                </a>
              </div>
            </div>
            <div className="mx-8 mt-3 mb-6 flex flex-col gap-2.5 rounded-[20px] border border-line px-5 py-[18px]">
              <div className="flex items-baseline justify-between">
                <span className="flex items-baseline gap-2.5">
                  <span className="font-serif text-[24px] leading-none text-ink italic">
                    Chapters
                  </span>
                  <span className="text-[16px] text-mute">
                    설명란에서 찾은 구간 · 분석에 사용돼요
                  </span>
                </span>
                <span className="text-[16px] font-semibold text-navy">{chapters.length}개</span>
              </div>
              {chapters.map((c) => (
                <div key={c.time} className="flex items-baseline gap-4 border-t border-line py-2">
                  <span className="w-11 text-[16px] font-semibold text-navy tabular">{c.time}</span>
                  <span className="text-[18px] text-ink">{c.label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : apiFail ? (
          <div className="mx-8 my-6 flex items-center justify-between gap-4 rounded-[20px] border border-line p-6">
            <span className="text-[17px] leading-[1.5] text-mute">
              검색에 실패했어요. 결과가 없는 게 아니라 일시적인 문제예요.
            </span>
            <button
              type="button"
              onClick={onRetry}
              className="shrink-0 text-[17px] font-bold text-navy"
            >
              다시 시도
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-[22px] pt-2 pb-6">
            {list.map((v, i) => {
              const st = stateOf(v);
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => setSel(v)}
                  className="flex flex-col gap-3 text-left"
                >
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
                        KW_BG[i % 3],
                      )}
                    >
                      {v.ch.slice(-1)}
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="text-[19px] leading-[1.35] font-semibold text-ink">
                        {v.title}
                      </span>
                      <span className="text-[16px] text-mute">
                        {v.ch} · {v.meta}
                      </span>
                      <span className="flex flex-wrap gap-1.5">
                        {st === "guide" && <GuideBadge />}
                        {st === "blocked" && (
                          <span className="mt-1 flex h-7 items-center rounded-full bg-cream px-2.5 text-[14px] font-bold text-mute">
                            재생 불가
                          </span>
                        )}
                      </span>
                    </span>
                  </div>
                </button>
              );
            })}
            {results.length === 0 && (
              <span className="px-6 py-7 text-[18px] text-mute">
                검색 결과가 없어요. 다른 단어로 찾아보세요.
              </span>
            )}
          </div>
        )}
      </div>

      {sel && (
        <div className="flex shrink-0 gap-2.5 border-t border-line px-10 pt-4 pb-6">
          <PillButton variant="line" size="hero" onClick={() => setSel(null)}>
            다른 영상
          </PillButton>
          {selState === "blocked" ? (
            <div className="ml-auto flex h-20 min-w-[300px] items-center justify-center rounded-full bg-line px-8 text-[21px] font-bold text-mute">
              선택할 수 없는 영상
            </div>
          ) : (
            <PillButton
              size="hero"
              trailing
              onClick={() => onPick(sel)}
              className="ml-auto min-w-[300px]"
            >
              <span className="tracking-[-.01em]">
                {selState === "guide" ? "바로 따라 하기" : "이 영상으로 메이크업 분석하기"}
              </span>
            </PillButton>
          )}
        </div>
      )}
      {/* 데모 전용 닫기 보조 (키보드) */}
      <button type="button" className="sr-only" onClick={onClose}>
        <X aria-hidden /> 닫기
      </button>
    </div>
  );
}

export function GuideBadge() {
  return (
    <span className="mt-1 flex h-7 items-center gap-1.5 self-start rounded-full bg-mint px-2.5 text-[14px] font-bold text-ink">
      <Check className="size-3" strokeWidth={3} aria-hidden />
      가이드 있음 · 바로 따라 하기
    </span>
  );
}
