"use client";

import { ArrowRight, Check, ChevronLeft, Lock, Play, Search, Trophy, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FlowSteps } from "@/components/flow-steps";
import { IconButton } from "@/components/ui/icon-button";
import { Notice } from "@/components/ui/notice";
import { useSession } from "@/features/session";
import { CHAPTERS, VIDEOS, videoThumb, type VideoItem, type VideoState } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const KEYWORDS = ["데일리", "코랄 블러셔", "봄 웜톤", "10분 메이크업", "무쌍 섀도", "글로시 립"];
const KW_BG = ["bg-pink-soft", "bg-lime", "bg-sky"];
const TOP_VIEWS = ["312만회", "248만회", "196만회", "153만회"];

// ponytail: API-VIDEO-001 응답을 흉내 낸 샘플 분기. y2 가이드 있음 · y3 분석 중 · y5 재생 불가 · y6 일일 한도
function videoState(v: VideoItem | null): VideoState {
  if (!v) return "new";
  return (
    ({ y2: "guide", y3: "running", y5: "blocked", y6: "quota" } as Record<string, VideoState>)[
      v.id
    ] ?? "new"
  );
}

/** 03 영상 입력 (VIDEO-001 · VIDEO-002 · VIDEO-005) */
export default function SelectPage() {
  const router = useRouter();
  const { startRun } = useSession();
  const [picked, setPicked] = useState<VideoItem | null>(null);
  const [picker, setPicker] = useState(false);
  const [query, setQuery] = useState("");
  const [sel, setSel] = useState<VideoItem | null>(null);
  const [playing, setPlaying] = useState(false);
  const [quota, setQuota] = useState(false);
  // ?fail=1: 검색·Top 4 조회 실패 확인용. 실제 API가 붙으면 오류 응답으로 바뀐다.
  const [apiFail, setApiFail] = useState(false);
  const params = useQuery();
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 상태를 한 번 반영한다
    setApiFail(params?.get("fail") === "1");
  }, [params]);

  const start = (v: VideoItem) => {
    const st = videoState(v);
    if (st === "blocked") return;
    if (st === "quota") {
      setPicked(v);
      setPicker(false);
      setQuota(true);
      return;
    }
    startRun({ picked: v, replay: st === "guide" ? "guide" : null });
    router.push(st === "running" ? "/loading?joined=1" : "/loading");
  };

  const openPicker = (q = "") => {
    setPicker(true);
    setQuery(q);
    setSel(null);
    setPlaying(false);
  };

  const q = query.trim();
  const results = VIDEOS.filter((v) => !q || v.title.includes(q) || v.ch.includes(q));
  const list = results.length ? results : VIDEOS;
  const selState = videoState(sel);
  const pickedState = videoState(picked);

  return (
    <main className="relative flex min-h-dvh flex-1 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton size={44} onClick={() => router.push("/home")} title="홈" aria-label="홈" />
        <span className="font-serif text-[28px] leading-none text-plum italic">New look</span>
        <span className="text-[17px] text-mute">레퍼런스 영상 가져오기</span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-10 pt-7 pb-8">
        <FlowSteps step={0} />
        <h1 className="font-display text-[32px] leading-[1.3] text-ink">
          따라 하고 싶은 메이크업
          <br />
          영상을 가져와요
        </h1>

        {quota && (
          <Notice tone="error" title="오늘 새로 분석할 수 있는 횟수를 다 썼어요">
            내일 다시 시도하거나, &apos;가이드 있음&apos; 표시가 있는 영상은 바로 따라 할 수 있어요.
          </Notice>
        )}

        {picked && (
          <div className="flex flex-col gap-3.5">
            <div className="relative aspect-video overflow-hidden rounded-[20px] border border-line bg-white">
              <div
                className="absolute inset-0 bg-cover bg-center"
                style={{ backgroundImage: `url(${videoThumb(picked.ytid)})` }}
              />
              <span className="absolute top-4 left-4 rounded-full bg-white px-3 py-[7px] font-label text-[15px] font-semibold tracking-[.14em] text-plum">
                YOUTUBE
              </span>
              <span className="absolute right-4 bottom-4 rounded-lg bg-ink px-2 py-1 text-[16px] font-semibold text-white tabular">
                {picked.dur}
              </span>
              <span className="absolute top-1/2 left-1/2 flex size-[72px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white">
                <Play className="size-[26px] fill-plum text-plum" aria-hidden />
              </span>
            </div>
            <div className="flex items-start justify-between gap-4">
              <span className="flex min-w-0 flex-col gap-1">
                <span className="font-display text-[22px] leading-[1.3] text-ink">
                  {picked.title}
                </span>
                <span className="text-[17px] text-mute">{picked.ch}</span>
              </span>
              <button
                type="button"
                onClick={() => {
                  setPicked(null);
                  setQuota(false);
                }}
                className="shrink-0 pt-1 text-[17px] font-semibold whitespace-nowrap text-plum"
              >
                다시 고르기
              </button>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3.5">
          <button
            type="button"
            onClick={() => openPicker()}
            className="flex h-[76px] items-center gap-3.5 rounded-full border-[1.5px] border-ink bg-white py-0 pr-2.5 pl-[26px] text-left hover:border-plum"
          >
            <Search className="size-[22px] text-ink" strokeWidth={1.8} aria-hidden />
            <span className="flex-1 text-[18px] text-mute">YouTube에서 메이크업 영상 검색</span>
            <span className="flex h-14 items-center rounded-full bg-plum px-[26px] text-[19px] font-semibold text-white">
              검색
            </span>
          </button>
          <div className="flex flex-wrap gap-2">
            {KEYWORDS.map((k, i) => (
              <button
                key={k}
                type="button"
                onClick={() => openPicker(k)}
                className={cn(
                  "flex h-10 items-center gap-1.5 rounded-full px-4 text-[17px] font-semibold text-ink",
                  KW_BG[i % 3],
                )}
              >
                <span className="font-serif text-[19px] text-plum italic">#</span>
                {k}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-3.5 border-t border-line pt-7">
          <div className="flex items-baseline gap-2.5">
            <span className="font-serif text-[26px] leading-none text-ink italic">
              Top 4 videos
            </span>
            <span className="text-[16px] text-mute">
              YouTube 인기 메이크업 영상 TOP 4 · 탭하면 바로 분석
            </span>
          </div>
          {apiFail ? (
            <div className="flex items-center justify-between gap-4 rounded-[20px] border border-line px-6 py-7">
              <span className="text-[17px] leading-[1.5] text-mute">
                인기 영상을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
              </span>
              <button
                type="button"
                onClick={() => setApiFail(false)}
                className="shrink-0 text-[17px] font-bold text-plum"
              >
                다시 시도
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3.5">
              {VIDEOS.slice(0, 4).map((v, i) => (
                <button
                  key={v.id}
                  type="button"
                  onClick={() => start(v)}
                  className="flex flex-col gap-2.5 rounded-[20px] border-2 border-transparent p-2 text-left hover:border-line"
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
                        i === 0 ? "bg-lime text-ink" : "bg-ink text-white",
                      )}
                    >
                      <Trophy className="size-[18px]" aria-hidden />
                      {i + 1}위
                    </span>
                  </div>
                  <span className="flex flex-col gap-1 px-1 pb-1">
                    <span className="font-display text-[17px] leading-[1.3] text-ink">
                      {v.title}
                    </span>
                    <span className="text-[16px] text-mute">YouTube · 조회수 {TOP_VIEWS[i]}</span>
                    {videoState(v) === "guide" && <GuideBadge />}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {picked && (
        <div className="flex shrink-0 animate-fade justify-end border-t border-line px-10 pt-5 pb-7">
          <button
            type="button"
            onClick={() => start(picked)}
            disabled={pickedState === "quota" || pickedState === "blocked"}
            className="flex h-[76px] min-w-[240px] items-center justify-center gap-3 rounded-full bg-pink px-[34px] text-[22px] font-bold text-white active:scale-[.97] disabled:bg-line disabled:text-mute"
          >
            {pickedState === "guide" ? "바로 따라 하기" : "이 영상으로 분석 시작"}
            <ArrowRight className="size-6" strokeWidth={2.4} aria-hidden />
          </button>
        </div>
      )}

      {picker && (
        <div className="absolute inset-0 z-10 flex flex-col bg-white">
          <div className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
            <IconButton
              size={44}
              icon="close"
              onClick={() => setPicker(false)}
              title="닫기"
              aria-label="닫기"
            />
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
                  className="flex items-center gap-2 px-8 pb-3 text-left text-[17px] font-semibold text-plum"
                >
                  <ChevronLeft className="size-4" strokeWidth={2} aria-hidden />
                  검색 결과로
                </button>
                <div className="relative aspect-video bg-black">
                  {selState === "blocked" && (
                    <div
                      data-dark
                      className="absolute inset-0 z-[2] flex flex-col items-center justify-center gap-2.5 bg-[rgba(8,13,34,.82)] p-6 text-center text-white"
                    >
                      <span className="text-[21px] font-bold">
                        이 영상은 mairor에서 재생할 수 없어요
                      </span>
                      <span className="text-[16px] leading-[1.5] text-line-2">
                        업로더가 외부 재생을 막았거나 비공개·삭제된 영상이에요. 다른 영상을 골라
                        주세요.
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
                        <Play className="size-[30px] fill-plum text-plum" aria-hidden />
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
                  <span className="text-[21px] leading-[1.35] font-semibold text-ink">
                    {sel.title}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="flex size-10 items-center justify-center rounded-full bg-pink-soft text-[18px] font-bold text-ink">
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
                      className="ml-auto text-[16px] font-semibold text-plum"
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
                    <span className="text-[16px] font-semibold text-plum">{CHAPTERS.length}개</span>
                  </div>
                  {CHAPTERS.map((c) => (
                    <div
                      key={c.time}
                      className="flex items-baseline gap-4 border-t border-line py-2"
                    >
                      <span className="w-11 text-[16px] font-semibold text-plum tabular">
                        {c.time}
                      </span>
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
                  onClick={() => setApiFail(false)}
                  className="shrink-0 text-[17px] font-bold text-plum"
                >
                  다시 시도
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-[22px] pt-2 pb-6">
                {list.map((v, i) => {
                  const st = videoState(v);
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
              <button
                type="button"
                onClick={() => setSel(null)}
                className="flex h-20 shrink-0 items-center justify-center rounded-full border-2 border-line px-[30px] text-[21px] font-bold whitespace-nowrap text-ink active:scale-[.96]"
              >
                다른 영상
              </button>
              {selState === "blocked" ? (
                <div className="ml-auto flex h-20 min-w-[300px] items-center justify-center rounded-full bg-line px-8 text-[21px] font-bold text-mute">
                  선택할 수 없는 영상
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setPicked(sel);
                    setPicker(false);
                    setQuota(false);
                  }}
                  className="ml-auto flex h-20 min-w-[300px] items-center justify-between gap-6 rounded-full bg-pink py-0 pr-2.5 pl-8 text-white shadow-[0_14px_30px_color-mix(in_srgb,var(--color-pink)_26%,transparent)] active:scale-[.97]"
                >
                  <span className="truncate text-[23px] font-bold tracking-[-.01em]">
                    {selState === "guide" ? "바로 따라 하기" : "이 영상으로 메이크업 분석하기"}
                  </span>
                  <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                    <ArrowRight className="size-7" strokeWidth={2.4} aria-hidden />
                  </span>
                </button>
              )}
            </div>
          )}
          {/* 데모 전용 닫기 보조 (키보드) */}
          <button type="button" className="sr-only" onClick={() => setPicker(false)}>
            <X aria-hidden /> 닫기
          </button>
        </div>
      )}
    </main>
  );
}

function GuideBadge() {
  return (
    <span className="mt-1 flex h-7 items-center gap-1.5 self-start rounded-full bg-lime px-2.5 text-[14px] font-bold text-ink">
      <Check className="size-3" strokeWidth={3} aria-hidden />
      가이드 있음 · 바로 따라 하기
    </span>
  );
}
