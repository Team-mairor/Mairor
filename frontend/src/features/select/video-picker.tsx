"use client";

import { Check, ChevronLeft, Lock, Play, Search, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { PillButton } from "@/components/ui/pill-button";
import { toChapter, toVideoItem, videoThumb, type VideoItem } from "@/features/video";
import { ApiError, errorMessage, type VideoSelection } from "@/lib/api";
import { cn } from "@/lib/utils";

import { targetOfSelection } from "./start-target";
import { useVideoSearch, useVideoSelection } from "./video-api";

/** 키워드 칩·채널 동그라미 배경 (돌아가며 쓴다) */
export const KW_BG = ["bg-blush", "bg-mint", "bg-sky"];

/** 검색어 없이 열면 이 말로 찾는다 */
const DEFAULT_QUERY = "메이크업";

const isUnsupported = (e: unknown) =>
  e instanceof ApiError && e.code === "VIDEO_UNSUPPORTED_FOR_ANALYSIS";

/**
 * 앱 안에서 여는 YouTube 검색 화면 (API-VIDEO-004 · API-VIDEO-001). 검색 → 영상 미리보기(재생·챕터) → 고르기.
 * 영상을 누르면 선택 API로 라이선스·가이드 유무·챕터를 받는다. 분석할 수 있는 영상이면 onPick을 부르고,
 * 부모가 바로 따라 하기 · 진행 중 분석 보기 · 새 분석 요청(API-VIDEO-002) 중 하나로 시작한다. 시작이 실패하면 그 오류를 여기 보여 준다.
 * 열 때마다 새로 그리므로 검색어·선택 영상은 여기서만 들고 있다
 */
export function VideoPicker({
  initialQuery,
  onClose,
  onPick,
}: {
  initialQuery: string;
  onClose: () => void;
  onPick: (video: VideoItem, selection: VideoSelection) => Promise<void> | void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  /** 실제로 검색한 말. 입력하고 검색(Enter)할 때 바뀐다 */
  const [term, setTerm] = useState(initialQuery.trim() || DEFAULT_QUERY);
  const [sel, setSel] = useState<VideoItem | null>(null);
  const [playing, setPlaying] = useState(false);
  /** 시작(분석 요청) 중이면 버튼을 막고, 실패하면 오류를 보여 준다 */
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<unknown>(null);

  const search = useVideoSearch(term);
  const selection = useVideoSelection(sel?.ytid ?? null);
  const picked = selection.load.status === "ready" ? selection.load.data : null;
  const selError = selection.load.status === "error" ? selection.load.error : null;
  const blocked = isUnsupported(selError);
  const target = picked ? targetOfSelection(picked) : null;
  const start = async (video: VideoItem, selection: VideoSelection) => {
    setStarting(true);
    setStartError(null);
    try {
      await onPick(video, selection);
    } catch (e) {
      setStartError(e);
    } finally {
      setStarting(false);
    }
  };
  const chapters = picked?.chapters.map(toChapter) ?? [];

  const searchError = search.load.status === "error" ? search.load.error : null;
  useEffect(() => {
    const e = searchError ?? selError ?? startError;
    if (e instanceof ApiError && e.code === "UNAUTHORIZED") router.replace("/login?expired=basic");
  }, [searchError, selError, startError, router]);

  const q = query.trim();
  const list = search.load.status === "ready" ? search.load.data.items : [];

  return (
    <div className="absolute inset-0 z-10 flex flex-col bg-white">
      <div className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton size={44} icon="close" onClick={onClose} title="닫기" aria-label="닫기" />
        <span className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-full bg-cream px-4">
          <Lock className="size-3.5 text-mute" strokeWidth={2} aria-hidden />
          <span className="truncate text-[17px] text-ink">
            YouTube 검색 · {term === DEFAULT_QUERY ? term : `"${term}"`}
          </span>
        </span>
        <span className="text-[16px] font-semibold whitespace-nowrap text-mute">
          mairor 안에서 열림
        </span>
      </div>
      {!sel && (
        <div className="shrink-0 px-7 pt-4">
          <form
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              setTerm(q || DEFAULT_QUERY);
            }}
          >
            <label className="flex h-[52px] items-center gap-2.5 rounded-full border border-line px-[18px]">
              <Search className="size-[18px] text-mute" strokeWidth={1.8} aria-hidden />
              <input
                type="search"
                enterKeyHint="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="메이크업 영상 검색"
                className="min-w-0 flex-1 bg-transparent text-[19px] text-ink outline-none"
                autoFocus
              />
            </label>
          </form>
        </div>
      )}

      <div className="scrollbar-hidden flex min-h-0 flex-1 flex-col overflow-y-auto pt-4">
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
              {blocked && (
                <div
                  data-dark
                  className="absolute inset-0 z-[2] flex flex-col items-center justify-center gap-2.5 bg-night/80 p-6 text-center text-white"
                >
                  <span className="text-[21px] font-bold">이 영상은 분석할 수 없어요</span>
                  <span className="text-[16px] leading-[1.5] text-line-2">
                    {errorMessage(selError)} 다른 영상을 골라 주세요.
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
                <span className="text-[16px] font-semibold text-navy">
                  {picked ? `${chapters.length}개` : ""}
                </span>
              </div>
              {selection.load.status === "loading" && (
                <span className="border-t border-line py-2 text-[17px] text-mute">
                  영상 정보를 확인하고 있어요
                </span>
              )}
              {picked && chapters.length === 0 && (
                <span className="border-t border-line py-2 text-[17px] text-mute">
                  설명란에 챕터가 없어요
                </span>
              )}
              {chapters.map((c) => (
                <div key={c.time} className="flex items-baseline gap-4 border-t border-line py-2">
                  <span className="w-11 text-[16px] font-semibold text-navy tabular">{c.time}</span>
                  <span className="text-[18px] text-ink">{c.label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : searchError ? (
          <div className="mx-8 my-6 flex items-center justify-between gap-4 rounded-[20px] border border-line p-6">
            <span className="text-[17px] leading-[1.5] text-mute">
              {errorMessage(searchError)} 결과가 없는 게 아니라 일시적인 문제예요.
            </span>
            <button
              type="button"
              onClick={search.retry}
              className="shrink-0 text-[17px] font-bold text-navy"
            >
              다시 시도
            </button>
          </div>
        ) : search.load.status === "loading" ? (
          <span className="px-8 py-7 text-[18px] text-mute">검색하고 있어요</span>
        ) : (
          <div className="flex flex-col gap-[22px] pt-2 pb-6">
            {list.map((item, i) => {
              const v = toVideoItem(item);
              return (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => {
                    setSel(v);
                    setPlaying(false);
                  }}
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
                      {item.guideAvailable && <GuideBadge />}
                    </span>
                  </div>
                </button>
              );
            })}
            {list.length === 0 && (
              <span className="px-6 py-7 text-[18px] text-mute">
                분석할 수 있는(CC BY) 영상을 찾지 못했어요. 다른 단어로 찾아보세요.
              </span>
            )}
          </div>
        )}
      </div>

      {sel && (
        <div className="flex shrink-0 flex-col gap-3 border-t border-line px-10 pt-4 pb-6">
          {(selError && !blocked) || startError ? (
            <span className="text-[16px] leading-[1.5] text-error" role="alert">
              {errorMessage(startError ?? selError)}
            </span>
          ) : null}
          <div className="flex gap-2.5">
            <PillButton
              variant="line"
              size="hero"
              onClick={() => {
                setSel(null);
                setStartError(null);
              }}
            >
              다른 영상
            </PillButton>
            {selError && !blocked ? (
              <PillButton size="hero" onClick={selection.retry} className="ml-auto min-w-[300px]">
                다시 확인
              </PillButton>
            ) : picked ? (
              <PillButton
                size="hero"
                trailing
                disabled={starting}
                onClick={() => void start(sel, picked)}
                className="ml-auto min-w-[300px]"
              >
                <span className="tracking-[-.01em]">
                  {starting
                    ? "분석 요청 중"
                    : target?.kind === "guide"
                      ? "바로 따라 하기"
                      : target?.kind === "job"
                        ? "분석 진행 보기"
                        : "이 영상으로 메이크업 분석하기"}
                </span>
              </PillButton>
            ) : (
              <PillButton size="hero" disabled className="ml-auto min-w-[300px]">
                {blocked ? "선택할 수 없는 영상" : "영상 확인 중"}
              </PillButton>
            )}
          </div>
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
