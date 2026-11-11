"use client";

import { ArrowRight, Play, Search, Trophy } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { FlowSteps } from "@/components/flow-steps";
import { IconButton } from "@/components/ui/icon-button";
import { Notice } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import {
  GuideBadge,
  KW_BG,
  requestAnalysis,
  targetOfReceipt,
  targetOfSelection,
  VideoPicker,
} from "@/features/select";
import { runHref, useSession } from "@/features/session";
import { videoThumb, type VideoItem } from "@/features/video";
import type { VideoSelection } from "@/lib/api";
import { useQuery } from "@/lib/hooks/use-query";
import { cn } from "@/lib/utils";
import { VIDEOS, videoState } from "@/mocks/mock-data";

const KEYWORDS = ["데일리", "코랄 블러셔", "봄 웜톤", "10분 메이크업", "무쌍 섀도", "글로시 립"];
const TOP_VIEWS = ["312만회", "248만회", "196만회", "153만회"];

/**
 * 03 영상 입력 (VIDEO-004 · VIDEO-001 · VIDEO-002). 검색 · 선택 · 분석 요청은 실제 API를 쓴다.
 * Top 4(VIDEO-005)는 아직 샘플이다
 */
export default function SelectPage() {
  const router = useRouter();
  const { startRun } = useSession();
  const [picked, setPicked] = useState<VideoItem | null>(null);
  /** 검색 화면에 넣을 첫 검색어. null이면 닫힘 */
  const [picker, setPicker] = useState<string | null>(null);
  const [quota, setQuota] = useState(false);
  // ?fail=1: 검색·Top 4 조회 실패 확인용. 실제 API가 붙으면 오류 응답으로 바뀐다.
  const [apiFail, setApiFail] = useState(false);
  const params = useQuery();
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 상태를 한 번 반영한다
    setApiFail(params?.get("fail") === "1");
  }, [params]);

  // 실제 영상을 한 번 시작하면 화면을 떠날 때까지 다시 시작하지 않는다(연타로 분석이 두 번 요청되지 않게)
  const started = useRef(false);

  /**
   * 검색에서 고른 영상으로 시작한다. 승인 가이드가 있으면 바로 따라 하기, 내가 요청한 분석이 진행 중이면 그 작업으로,
   * 아니면 분석을 요청해(API-VIDEO-002) 받은 작업의 로딩 화면으로 간다. 요청이 실패하면 오류를 검색 화면에 넘긴다
   */
  const startPicked = async (v: VideoItem, s: VideoSelection) => {
    if (started.current) return;
    started.current = true;
    try {
      const target = targetOfSelection(s) ?? targetOfReceipt(await requestAnalysis(s.videoId));
      // 계약상 비지 않지만, 비면 어디로도 가지 않고 다시 누를 수 있게 둔다
      if (!target) throw new Error("분석 요청 응답에 시작할 ID가 없다");
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

  /** Top 4 샘플 영상 */
  const start = (v: VideoItem) => {
    const st = videoState(v);
    if (st === "blocked") return;
    if (st === "quota") {
      setPicked(v);
      setPicker(null);
      setQuota(true);
      return;
    }
    startRun({ kind: "sample", picked: v, replay: st === "guide" ? "guide" : null });
    router.push(st === "running" ? "/loading?joined=1" : "/loading");
  };

  const openPicker = (q = "") => setPicker(q);

  const pickedState = videoState(picked);

  return (
    <main className="relative flex min-h-dvh flex-1 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton size={44} onClick={() => router.push("/home")} title="홈" aria-label="홈" />
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
              <span className="absolute top-4 left-4 rounded-full bg-white px-3 py-[7px] font-label text-[15px] font-semibold tracking-[.14em] text-navy">
                YOUTUBE
              </span>
              <span className="absolute right-4 bottom-4 rounded-lg bg-ink px-2 py-1 text-[16px] font-semibold text-white tabular">
                {picked.dur}
              </span>
              <span className="absolute top-1/2 left-1/2 flex size-[72px] -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white">
                <Play className="size-[26px] fill-navy text-navy" aria-hidden />
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
                className="shrink-0 pt-1 text-[17px] font-semibold whitespace-nowrap text-navy"
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
                className="shrink-0 text-[17px] font-bold text-navy"
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
                        i === 0 ? "bg-mint text-ink" : "bg-ink text-white",
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
          <PillButton
            size="hero"
            onClick={() => start(picked)}
            disabled={pickedState === "quota" || pickedState === "blocked"}
            className="min-w-[240px]"
          >
            {pickedState === "guide" ? "바로 따라 하기" : "이 영상으로 분석 시작"}
            <ArrowRight className="size-6" strokeWidth={2.4} aria-hidden />
          </PillButton>
        </div>
      )}

      {picker !== null && (
        <VideoPicker
          initialQuery={picker}
          onClose={() => setPicker(null)}
          // 검색 화면의 버튼이 곧 시작이다. 이 화면으로 돌아와 한 번 더 누르지 않는다
          onPick={startPicked}
        />
      )}
    </main>
  );
}
