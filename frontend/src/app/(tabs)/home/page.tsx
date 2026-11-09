"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { Modal } from "@/components/ui/modal";
import { FieldError } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { useLogout } from "@/features/auth";
import { PouchBoard, usePouchSync } from "@/features/pouch";
import { displayName, useSession } from "@/features/session";
import { videoThumb } from "@/features/video";
import { useQuery } from "@/lib/hooks/use-query";
import { VIDEOS } from "@/mocks/mock-data";

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

/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */

/** 02 홈 (REPORT-002 · REPORT-005 · POUCH-004 · VIDEO-003 검수 카드) */
export default function HomePage() {
  const router = useRouter();
  const { state, sessionChecked, update, startRun } = useSession();
  // 로그인했으면 파우치 보드를 서버 목록으로 맞춘다 (API-POUCH-003)
  const sync = usePouchSync();
  const [account, setAccount] = useState(false);
  const { logout, pending: logoutPending, error: logoutError } = useLogout();
  const query = useQuery();
  // ?empty=1: 리포트·파우치 빈 상태 확인용 (데이터는 지우지 않는다)
  const empty = query?.get("empty") === "1";
  const reports = empty ? [] : state.reports;
  // 로그인했으면 서버 목록을 받기 전·받지 못했을 때 저장된(지난) 파우치를 보여 주지 않는다 (내 파우치와 같다)
  const waiting = sync.status === "loading" || (state.loggedIn && !sessionChecked);
  const hidden = waiting || sync.status === "error";
  const pouch = empty || hidden ? [] : state.pouch;
  const d = new Date();
  const today = `${DAYS[d.getDay()]}, ${MONTHS[d.getMonth()]} ${d.getDate()}`;
  const last = reports[0];
  const pg = empty ? null : state.pendingGuide;
  const approved = pg?.status === "approved";

  /** 다시 따라 하기: 분석 없이 준비 단계(얼굴 등록 → 파우치 확인)부터 */
  const replayLast = () => {
    // 기록에 남은 영상으로 다시 시작한다. 샘플 기록처럼 영상 id가 없으면 첫 영상
    const v = VIDEOS.find((x) => x.id === last?.videoId) ?? VIDEOS[0];
    startRun({ picked: v, replay: "report" });
    router.push("/loading");
  };
  const startPending = () => {
    const v = VIDEOS.find((x) => x.ytid === pg?.ytid) ?? VIDEOS[0];
    startRun({ picked: v, replay: "guide" });
    update({ pendingGuide: null });
    router.push("/loading");
  };

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <header className="flex h-[68px] shrink-0 items-center gap-3 px-8">
        <span className="font-serif text-[40px] leading-none tracking-[-.02em] text-navy italic">
          mairor
        </span>
        <button
          type="button"
          onClick={() => setAccount(true)}
          className="ml-auto flex size-11 items-center justify-center rounded-full bg-mint font-serif text-[22px] text-ink italic"
          aria-label="계정 · 로그아웃"
        >
          {(displayName(state).trim()[0] ?? "m").toUpperCase()}
        </button>
      </header>

      {/* 잘못 눌러 바로 로그아웃되지 않게 한 번 묻는다. 로그인 뒤 미러필름 모드를 바꿀 곳도 여기다 */}
      <Modal
        open={account}
        onClose={() => !logoutPending && setAccount(false)}
        labelledBy="account-title"
        // 하단 탭까지 덮어, 창이 떠 있는 동안 다른 화면으로 가지 않게 한다
        overlayClassName="fixed z-40"
        className="flex max-w-[520px] flex-col gap-6 px-[30px] pt-8 pb-6"
      >
        <div className="flex flex-col gap-2">
          <h2 id="account-title" className="font-display text-[30px] leading-[1.25] text-ink">
            로그아웃할까요?
          </h2>
          <p className="text-[17px] text-mute">{state.email}</p>
        </div>
        <MirrorToggle className="justify-between" />
        {logoutError && <FieldError>{logoutError}</FieldError>}
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => setAccount(false)}
            disabled={logoutPending}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[19px] font-bold text-ink"
          >
            취소
          </button>
          <PillButton
            variant="dark"
            className="h-[68px] flex-1"
            busy={logoutPending}
            onClick={logout}
          >
            {logoutPending ? "로그아웃 중" : "로그아웃"}
          </PillButton>
        </div>
      </Modal>

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
          <Link
            href="/select"
            className="flex min-w-0 flex-col justify-between rounded-3xl bg-navy p-6 hover:brightness-90"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="font-label text-[15px] font-semibold tracking-[.16em] text-blush">
                NEW LOOK
              </span>
              <span className="flex size-14 shrink-0 items-center justify-center rounded-full bg-mint text-ink">
                <Plus className="size-[26px]" strokeWidth={1.8} aria-hidden />
              </span>
            </div>
            <div className="flex flex-col gap-3.5">
              <span className="font-display text-[28px] leading-[1.3] text-white">
                새 메이크업
                <br />
                영상 추가
              </span>
              <span className="self-start rounded-full bg-white px-[11px] py-1.5 text-[16px] font-semibold text-ink">
                YouTube 검색
              </span>
            </div>
          </Link>

          {last ? (
            <div className="grid min-w-0 grid-cols-[minmax(0,.9fr)_minmax(0,1fr)] gap-[18px] rounded-3xl border border-line bg-white p-3.5">
              <div className="relative min-h-0 overflow-hidden rounded-2xl">
                <img
                  src="/images/login-editorial.png"
                  alt=""
                  className="absolute inset-0 h-full w-full object-cover object-[50%_32%]"
                />
              </div>
              <div className="flex min-w-0 flex-col justify-between py-2 pr-2">
                <div className="flex flex-col gap-2.5">
                  <span className="flex items-baseline gap-2">
                    <span className="font-serif text-[26px] leading-none text-ink italic">
                      Again
                    </span>
                    <span className="text-[16px] text-mute">지난 가이드 다시 따라 하기</span>
                  </span>
                  <span className="font-display text-[21px] leading-[1.3] text-pretty text-ink">
                    {last.title}
                  </span>
                </div>
                <div className="flex flex-col gap-2.5">
                  <span className="text-[15px] text-mute tabular">
                    {last.date} 완료 · {last.steps}단계
                  </span>
                  <PillButton size="md" className="mt-1 h-12 text-[18px]" onClick={replayLast}>
                    다시 하기
                  </PillButton>
                </div>
              </div>
            </div>
          ) : (
            <Link
              href="/select"
              className="flex min-w-0 flex-col justify-center gap-2.5 rounded-3xl border-[1.5px] border-dashed border-line-2 bg-white p-6 hover:border-navy"
            >
              <span className="font-serif text-[26px] leading-none text-navy italic">
                First look
              </span>
              <span className="font-display text-[22px] leading-[1.35] text-pretty text-ink">
                첫 메이크업을 시작해 보세요
              </span>
              <span className="text-[16px] leading-[1.5] text-pretty text-mute">
                영상을 골라 따라 하면 이곳에 다시 따라 할 수 있는 룩이 생겨요.
              </span>
            </Link>
          )}
        </div>

        {pg && (
          <div className="flex min-w-0 shrink-0 items-center gap-[18px] rounded-3xl border border-line bg-white p-3.5">
            <span
              className="h-20 w-[120px] shrink-0 rounded-[14px] bg-cover bg-center"
              style={{
                backgroundImage: `url(${pg.ytid ? videoThumb(pg.ytid) : "/images/login-editorial.png"})`,
              }}
            />
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <span className="font-label text-[14px] font-semibold tracking-[.14em] text-navy">
                {approved ? "READY" : "IN REVIEW"}
              </span>
              <span className="truncate font-display text-[20px] leading-[1.3] text-ink">
                {pg.title}
              </span>
              <span className="truncate text-[16px] text-mute">
                {approved
                  ? "검수 완료 · 지금 따라 할 수 있어요"
                  : "검수 중 · 끝나면 여기서 바로 시작해요"}
              </span>
            </div>
            {approved && (
              <PillButton size="md" className="h-14 shrink-0 text-[18px]" onClick={startPending}>
                따라 하기
              </PillButton>
            )}
          </div>
        )}

        <PouchBoard
          items={pouch}
          scale={0.6}
          className="min-h-0 flex-1"
          onEdit={(p) => router.push(`/my/pouch?edit=${p.id}`)}
          stickerSize="lg"
        >
          <div className="absolute top-5 right-[22px] left-[22px] z-[2] flex items-start justify-between">
            <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
              <span className="font-serif text-[32px] leading-none text-ink italic">My pouch</span>
              {sync.status === "error" ? (
                <span className="flex items-center gap-2 text-[16px] text-mute">
                  파우치를 불러오지 못했어요
                  <button type="button" onClick={sync.retry} className="font-bold text-navy">
                    다시 시도
                  </button>
                </span>
              ) : waiting ? (
                <span className="text-[16px] text-mute">파우치를 불러오고 있어요</span>
              ) : (
                <span className="text-[16px] text-mute">
                  내 파우치 · {pouch.length}개 · 탭해서 수정
                </span>
              )}
            </span>
            <Link
              href="/my/pouch?add=1"
              className="flex h-11 items-center gap-2 rounded-full bg-ink px-[18px] text-[17px] font-semibold text-white"
            >
              <Plus className="size-4" strokeWidth={2} aria-hidden />
              제품 추가
            </Link>
          </div>
          {pouch.length === 0 && !hidden && (
            <div className="absolute inset-0 z-[1] flex flex-col items-center justify-center gap-3.5 px-10 pt-[90px] pb-6 text-center">
              <span className="font-display text-[24px] leading-[1.35] text-ink">
                파우치가 비어 있어요
              </span>
              <span className="max-w-[420px] text-[17px] leading-[1.5] text-pretty text-mute">
                가진 제품을 담아 두면 영상 속 제품과 비교해 바로 쓸 수 있는 것과 대체할 수 있는 것을
                알려 드려요.
              </span>
              <Link
                href="/my/pouch?add=1"
                className="flex h-12 items-center gap-2 rounded-full bg-ice px-[22px] text-[17px] font-semibold text-ink"
              >
                <Plus className="size-4" strokeWidth={2} aria-hidden />첫 제품 담기
              </Link>
            </div>
          )}
        </PouchBoard>

        <div className="flex shrink-0 flex-col gap-3">
          <div className="flex items-baseline justify-between gap-2.5">
            <span className="flex items-baseline gap-2.5">
              <span className="font-serif text-[34px] leading-none text-ink italic">Reports</span>
              <span className="text-[18px] text-mute">최근 리포트</span>
            </span>
            <Link href="/my/reports" className="text-[18px] font-semibold text-navy">
              전체 보기
            </Link>
          </div>
          {reports.length === 0 ? (
            <div className="flex items-center justify-between gap-4 rounded-[22px] border border-line bg-white px-6 py-[22px]">
              <span className="text-[17px] leading-[1.5] text-pretty text-mute">
                아직 완료한 메이크업이 없어요. 영상을 골라 따라 해 보세요.
              </span>
              <Link href="/select" className="shrink-0 text-[17px] font-bold text-navy">
                영상 고르기
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-3">
              {reports.slice(0, 3).map((r, i) => (
                <Link
                  key={r.id}
                  href={`/my/report?id=${r.id}`}
                  className="flex min-w-0 flex-col gap-2.5 rounded-[22px] border border-line bg-white px-2.5 pt-2.5 pb-3.5 hover:border-navy"
                >
                  <span className="relative h-[110px] w-full shrink-0 overflow-hidden rounded-[14px]">
                    <img
                      src="/images/login-editorial.png"
                      alt=""
                      className="absolute inset-0 h-full w-full scale-[1.6] object-cover"
                      style={{ objectPosition: ["50% 40%", "45% 60%", "55% 30%"][i] }}
                    />
                  </span>
                  <span className="flex min-w-0 flex-col gap-1 px-1.5">
                    <span className="truncate font-display text-[20px] leading-[1.3] text-ink">
                      {r.title}
                    </span>
                    <span className="text-[16px] text-mute">
                      {r.date} · {r.steps}단계
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
