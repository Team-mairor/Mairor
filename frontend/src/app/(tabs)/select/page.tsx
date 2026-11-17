"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { CoachTour, type TourStep } from "@/components/coach-tour";
import { FlowSteps } from "@/components/flow-steps";
import { Notice } from "@/components/ui/notice";
import { runHref, useRun, useTour } from "@/domain/session";
import { toVideoItem, videoThumb, type VideoItem } from "@/domain/video";
import {
  EXAMPLE_VIDEOS,
  KW_BG,
  PopularVideoCard,
  requestAnalysis,
  targetOfPopular,
  targetOfReceipt,
  targetOfSelection,
  usePopularVideos,
  VideoPicker,
  type StartTarget,
} from "@/features/select";
import { ApiError, errorMessage, type PopularVideoItem, type VideoSelection } from "@/lib/api";
import { cn } from "@/lib/utils";

const KEYWORDS = ["데일리", "코랄 블러셔", "봄 웜톤", "10분 메이크업", "무쌍 섀도", "글로시 립"];

const TOUR: TourStep[] = [
  {
    target: "select-search",
    title: "영상 검색",
    body: "따라 하고 싶은 메이크업 영상을 YouTube에서 찾아요.\n아래 키워드를 눌러 바로 검색할 수도 있어요.",
  },
  {
    target: "select-top",
    title: "인기 영상",
    body: "다른 사람들이 많이 고른 영상이에요.\n누르면 바로 시작하고, 가이드가 이미 있는 영상은 분석을 기다리지 않아요.",
  },
];

const isCode = (e: unknown, code: string) => e instanceof ApiError && e.code === code;

/**
 * 03 영상 입력. 검색 · 선택(VIDEO-004 · 001)은 검색 화면에서, 인기 Top 4(VIDEO-005)는 이 화면에서 고른다.
 * 어느 쪽이든 승인 가이드가 있으면 바로 따라 하기, 없으면 분석을 요청해(VIDEO-002) 그 작업의 로딩 화면으로 간다
 */
export default function SelectPage() {
  const router = useRouter();
  const { startRun } = useRun();
  /** 검색 화면에 넣을 첫 검색어. null이면 닫힘 */
  const [picker, setPicker] = useState<string | null>(null);
  const popular = usePopularVideos();
  /** Top 4를 눌러 시작하다 실패한 오류. 검색 화면의 실패는 검색 화면이 보여 준다 */
  const [popularError, setPopularError] = useState<unknown>(null);
  const [popularBusy, setPopularBusy] = useState(false);

  const loadError = popular.load.status === "error" ? popular.load.error : null;
  // 최근 많이 고른 영상이 아직 없으면 같은 자리에 예시 영상을 흐리게 보여 준다
  const popularExample = isCode(loadError, "VIDEO_POPULAR_UNAVAILABLE");
  const tour = useTour("select", popular.load.status !== "loading" && picker === null);
  useEffect(() => {
    const e = loadError ?? popularError;
    if (isCode(e, "UNAUTHORIZED")) router.replace("/login?expired=basic");
  }, [loadError, popularError, router]);

  // 영상을 한 번 시작하면 화면을 떠날 때까지 다시 시작하지 않는다(연타로 분석이 두 번 요청되지 않게)
  const started = useRef(false);
  // 분석 요청 중에 탭으로 떠났으면 응답이 와도 로딩 화면으로 가지 않는다
  const left = useRef(false);
  useEffect(() => {
    left.current = false;
    return () => {
      left.current = true;
    };
  }, []);

  /**
   * 고른 영상으로 시작한다. 이미 정해진 곳(승인 가이드 · 내 진행 중 작업)이 없으면 분석을 요청해 받은 곳으로 간다.
   * 실패하면 다시 누를 수 있게 잠금을 풀고 오류를 그대로 던진다
   */
  const begin = async (v: VideoItem, videoId: string, known: StartTarget | null) => {
    if (started.current) return;
    started.current = true;
    try {
      const target = known ?? targetOfReceipt(await requestAnalysis(videoId));
      // 계약상 비지 않지만, 비면 어디로도 가지 않고 다시 누를 수 있게 둔다
      if (!target) throw new Error("분석 요청 응답에 시작할 ID가 없다");
      if (left.current) return;
      if (target.kind === "guide") {
        startRun({ kind: "guide", guideId: target.guideId });
        router.push(runHref("/loading", target.guideId));
      } else {
        startRun({ kind: "sample", picked: v, jobId: target.jobId });
        router.push(`/loading?jobId=${encodeURIComponent(target.jobId)}`);
      }
    } catch (e) {
      started.current = false;
      throw e;
    }
  };

  /** 검색 화면에서 고른 영상. 오류는 검색 화면이 받아 보여 준다 */
  const startPicked = (v: VideoItem, s: VideoSelection) =>
    begin(v, s.videoId, targetOfSelection(s));

  /** 인기 영상은 늘 저장돼 있어 선택(VIDEO-001) 없이 videoId로 바로 요청한다 */
  const startPopular = async (item: PopularVideoItem) => {
    setPopularError(null);
    setPopularBusy(true);
    try {
      await begin(toVideoItem(item), item.videoId, targetOfPopular(item));
    } catch (e) {
      setPopularError(e);
    } finally {
      setPopularBusy(false);
    }
  };

  const openPicker = (q = "") => setPicker(q);

  return (
    <main className="relative flex min-h-0 flex-1 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-10">
        <span className="font-serif text-[28px] leading-none text-navy italic">New look</span>
        <span className="text-[17px] text-mute">레퍼런스 영상 가져오기</span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-10 pt-7 pb-8">
        <FlowSteps step={0} />
        <h1 className="font-display text-[32px] leading-[1.3] text-ink">
          따라 하고 싶은 메이크업
          <br />
          영상을 가져와요
        </h1>

        <div data-tour="select-search" className="flex flex-col gap-3.5">
          <button
            type="button"
            onClick={() => openPicker()}
            className="flex h-[76px] items-center gap-3.5 rounded-full border-[1.5px] border-ink bg-white py-0 pr-2.5 pl-[26px] text-left hover:border-navy"
          >
            <Search className="size-[22px] text-ink" strokeWidth={1.8} aria-hidden />
            <span className="flex-1 text-[18px] text-mute">YouTube에서 메이크업 영상 검색</span>
            <span className="flex h-14 items-center rounded-full bg-navy px-[26px] text-[19px] font-semibold text-white">
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
                <span className="font-serif text-[19px] text-navy italic">#</span>
                {k}
              </button>
            ))}
          </div>
        </div>

        <div
          data-tour="select-top"
          className="mt-4 flex flex-col gap-3.5 border-t border-line pt-7"
        >
          <div className="flex items-baseline gap-2.5">
            <span className="font-serif text-[26px] leading-none text-ink italic">
              Top 4 videos
            </span>
            <span className="text-[16px] text-mute">
              {popularExample
                ? "예시 · 많이 고른 영상이 생기면 여기에 보여요"
                : "최근 30일 mairor에서 많이 고른 영상 · 탭하면 바로 시작"}
            </span>
          </div>
          {popularError ? (
            <Notice tone="error" title={errorMessage(popularError)}>
              다른 영상을 고르거나 잠시 뒤 다시 눌러 주세요.
            </Notice>
          ) : null}
          {popular.load.status === "error" ? (
            popularExample ? (
              <div
                className="grid grid-cols-2 gap-3.5 opacity-40 grayscale mirror:opacity-70"
                inert
              >
                {EXAMPLE_VIDEOS.map((v) => (
                  <div key={v.id} className="flex flex-col gap-2.5 p-2">
                    <div
                      className="relative aspect-video overflow-hidden rounded-[14px] border border-line bg-cover bg-center"
                      style={{ backgroundImage: `url(${videoThumb(v.ytid)})` }}
                    >
                      <span className="absolute right-2 bottom-2 rounded-md bg-ink px-2.5 py-1 text-[16px] font-semibold text-white tabular">
                        {v.dur}
                      </span>
                    </div>
                    <span className="flex flex-col gap-1 px-1 pb-1">
                      <span className="font-display text-[17px] leading-[1.3] text-ink">
                        {v.title}
                      </span>
                      <span className="text-[16px] text-mute">{v.ch}</span>
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-between gap-4 rounded-[20px] border border-line px-6 py-7">
                <span className="text-[17px] leading-[1.5] text-mute">
                  인기 영상을 불러오지 못했어요. {errorMessage(loadError)}
                </span>
                <button
                  type="button"
                  onClick={popular.retry}
                  className="shrink-0 text-[17px] font-bold text-navy"
                >
                  다시 시도
                </button>
              </div>
            )
          ) : popular.load.status === "ready" ? (
            <div className="grid grid-cols-2 gap-3.5">
              {popular.load.data.items.map((item) => (
                <PopularVideoCard
                  key={item.videoId}
                  item={item}
                  busy={popularBusy}
                  onPick={() => void startPopular(item)}
                />
              ))}
            </div>
          ) : (
            <span className="px-1 py-7 text-[17px] text-mute">인기 영상을 불러오고 있어요</span>
          )}
        </div>
      </div>

      {picker !== null && (
        <VideoPicker
          initialQuery={picker}
          onClose={() => setPicker(null)}
          // 검색 화면의 버튼이 곧 시작이다. 이 화면으로 돌아와 한 번 더 누르지 않는다
          onPick={startPicked}
        />
      )}
      {tour.show && <CoachTour steps={TOUR} onDone={tour.done} />}
    </main>
  );
}
