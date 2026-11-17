"use client";

import { useRouter } from "next/navigation";

import { isGuideId, runHref, useRun } from "@/domain/session";

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

/** 02 홈. 최근 리포트·다시 하기·파우치·검수 카드(로그인하면 API-VIDEO-007) */
export function HomeView() {
  const router = useRouter();
  const { startRun } = useRun();
  const data = useHomeData();
  const { reports, reportsWaiting, reportsError, pg, ready } = data;
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
    <main className="flex min-h-0 flex-1 flex-col">
      <HomeHeader />

      <div className="flex min-h-0 flex-1 flex-col gap-[18px] px-10 pt-3 pb-6">
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
          compact={Boolean(last)}
        />

        <RecentReports reports={reports} note={reportNote} />
      </div>
    </main>
  );
}
