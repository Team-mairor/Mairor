"use client";

import { useRouter } from "next/navigation";

import { CoachTour, type TourStep } from "@/components/coach-tour";
import { isGuideId, runHref, useRun, useTour } from "@/domain/session";

import { HomeHeader } from "./home-header";
import { HomePouch } from "./home-pouch";
import { AgainCard, FirstLookCard, NewLookCard, NoteCard } from "./look-cards";
import { PendingGuideCard } from "./pending-guide-card";
import { RecentReports } from "./recent-reports";
import { useHomeData } from "./use-home-data";

const DAYS = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];
const MONTHS = [
  "JANUARY",
  "FEBRUARY",
  "MARCH",
  "APRIL",
  "MAY",
  "JUNE",
  "JULY",
  "AUGUST",
  "SEPTEMBER",
  "OCTOBER",
  "NOVEMBER",
  "DECEMBER",
];

const TOUR: TourStep[] = [
  {
    target: "home-mirror",
    title: "미러필름 모드",
    body: "하프미러 필름을 붙인 화면에서 켜요.\n화면이 검게 바뀌고, 카메라 영상 대신 거울에 비친 내 얼굴 위에 가이드를 그려요.\n처음 켜면 거울 맞추기로 눈 위치부터 맞춰요.",
  },
  {
    target: "home-new",
    title: "새 메이크업 시작",
    body: "따라 하고 싶은 메이크업 영상을 YouTube에서 찾아요.\n영상을 분석해 내 얼굴에 맞춘 단계별 가이드를 만들어 드려요.",
  },
  {
    target: "home-again",
    title: "다시 따라 하기",
    body: "완성한 룩은 여기에 남아요.\n분석을 기다리지 않고 같은 가이드로 바로 다시 따라 할 수 있어요.",
  },
  {
    target: "home-pouch",
    title: "내 파우치",
    body: "가진 화장품을 담아 두면 영상 속 제품과 비교해 그대로 쓸 것과 대체할 것을 골라 드려요.",
  },
  {
    target: "home-reports",
    title: "리포트",
    body: "끝까지 따라 하면 단계별 내 얼굴 사진과 사용한 제품이 리포트로 쌓여요.",
  },
  {
    target: "tabs",
    title: "하단 메뉴",
    body: "오늘네컷 촬영, 튜토리얼, 파우치, 리포트로 언제든 바로 옮겨 갈 수 있어요.",
  },
];

/** 02 홈. 최근 리포트·다시 하기·파우치·검수 카드(로그인하면 API-VIDEO-007) */
export function HomeView() {
  const router = useRouter();
  const { startRun } = useRun();
  const data = useHomeData();
  const { reports, reportsWaiting, reportsError, pg, ready } = data;
  const tour = useTour("home", !data.pouchWaiting && !reportsWaiting);
  const d = new Date();
  const today = `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;
  const last = reports[0];
  const reportNote = reportsError ? (
    <span className="flex items-center gap-3 text-[17px] leading-[1.5] text-mute">
      리포트를 불러오지 못했어요
      <button type="button" onClick={data.retryReports} className="font-bold text-navy">
        다시 시도
      </button>
    </span>
  ) : reportsWaiting ? (
    <span className="text-[17px] leading-[1.5] text-mute">리포트를 불러오고 있어요</span>
  ) : null;

  const replayLast = () => {
    if (!isGuideId(last?.guideId)) return router.push("/select");
    startRun({ kind: "guide", guideId: last.guideId, replay: "report" });
    router.push(runHref("/loading", last.guideId));
  };
  const startPending = () => {
    if (pg?.status !== "approved" || !isGuideId(pg.guideId)) return router.push("/select");
    startRun({ kind: "guide", guideId: pg.guideId, replay: "guide" });
    router.push(runHref("/loading", pg.guideId));
  };

  return (
    <main className="flex flex-1 flex-col">
      <HomeHeader />

      <div className="flex flex-1 flex-col gap-[18px] px-10 pt-3 pb-6">
        <div className="flex flex-col gap-2">
          <span className="font-label text-[16px] font-semibold tracking-[.16em] text-mute">
            {today}
          </span>
          <h1 className="font-display text-[34px] leading-[1.3] tracking-[-.01em] text-ink">
            안녕하세요,
            <br />
            오늘은 어떤 메이크업을 따라 해볼까요
          </h1>
        </div>

        <div className="grid h-[292px] shrink-0 grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] gap-4">
          <NewLookCard />
          {last ? (
            <AgainCard last={last} onReplay={replayLast} />
          ) : reportNote ? (
            <NoteCard>{reportNote}</NoteCard>
          ) : (
            <FirstLookCard />
          )}
        </div>

        {pg && <PendingGuideCard pg={pg} ready={ready} onStart={startPending} />}

        <HomePouch
          pouch={data.pouch}
          sync={data.sync}
          waiting={data.pouchWaiting}
          hidden={data.pouchHidden}
        />

        <RecentReports reports={reports} note={reportNote} />
      </div>
      {tour.show && <CoachTour steps={TOUR} onDone={tour.done} />}
    </main>
  );
}
