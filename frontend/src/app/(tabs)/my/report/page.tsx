"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactElement } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Modal } from "@/components/ui/modal";
import { groupSteps } from "@/features/guide";
import {
  captureTiles,
  deleteReport,
  fromRecord,
  guideReportRows,
  PhotoSlot,
  SHOW_STEP_PHOTOS,
  StepPhotoImg,
  useReport,
  type ReportRowPhoto,
} from "@/features/report";
import { useSession } from "@/features/session";
import { ApiError, errorMessage } from "@/lib/api";
import { useQuery } from "@/lib/hooks/use-query";

type DelState = null | "ask" | "busy" | "fail";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */

/** 단계 사진 자리. 이 기기에서 찍은 사진, 없으면 서버 기록의 사진 주소, 둘 다 없으면 값마다 한 가지 모양 */
function StepPhoto({ row, url }: { row: ReportRowPhoto; url?: string | null }): ReactElement {
  if (row.photo === "shot") return <StepPhotoImg photo={row.shot} crop />;
  if (row.photo === "slot" && url)
    return <img src={url} alt="" className="absolute inset-0 h-full w-full object-cover" />;
  switch (row.photo) {
    case "none":
      return (
        <div className="absolute inset-0 z-[1] flex items-center justify-center bg-cream text-[16px] font-bold text-mute">
          미촬영
        </div>
      );
    case "slot":
      return (
        <div className="absolute inset-0 flex items-center justify-center bg-cream-2 text-[16px] font-bold text-navy">
          사진 없음
        </div>
      );
    case "bare":
    case "sample":
      return (
        <div className="absolute inset-0 flex items-center justify-center bg-cream text-[16px] font-bold text-mute">
          사진 없음
        </div>
      );
  }
}

/** 리포트 상세·삭제. ?id=<리포트 id>. 로그인한 계정의 서버 기록을 표시한다. */
export default function ReportPage() {
  const router = useRouter();
  const query = useQuery();
  const { state, storageLoaded, sessionChecked, update } = useSession();
  const [expanded, setExpanded] = useState(true);
  const [del, setDel] = useState<DelState>(null);

  // 정확한 id로만 찾는다. 저장값 · 로그인 확인 전에는 판단을 미룬다
  const id = query?.get("id") ?? null;
  const account = sessionChecked && state.loggedIn ? state.email : null;
  const remote = useReport(account, id);
  const remoteError = remote.load.status === "error" ? remote.load.error : null;
  const rep = state.loggedIn
    ? remote.load.status === "ready"
      ? fromRecord(remote.load.data)
      : undefined
    : undefined;
  // 없는 기록(404)은 목록으로 보낸다
  const missing = state.loggedIn
    ? (!!query && !id) || (remoteError instanceof ApiError && remoteError.status === 404)
    : storageLoaded && !!query && !rep;
  useEffect(() => {
    if (missing) router.replace("/my/reports");
  }, [missing, router]);
  const waiting =
    state.loggedIn && !missing && (!sessionChecked || remote.load.status === "loading");

  const steps = rep?.guide ? guideReportRows(rep.guide, rep.runId) : [];
  const tiles = captureTiles(steps);
  // 부위를 아는 묶음의 첫 단계 앞에 부위 이름을 띄운다
  const heads = new Map(
    groupSteps(steps)
      .filter((g) => g.category)
      .map((g) => [g.start, g.label]),
  );
  const hasFinal =
    !!rep && !rep.noPhoto && (rep.finalPhoto ?? Boolean(rep.photoUrl || rep.runId || rep.guide));
  const last = steps.at(-1);
  const finalShot = last?.photo === "shot" ? last.shot : null;
  // 단계 사진 목록. 실제 가이드 기록은 보여 줄지를 따로 정한다
  const showSteps = (!rep?.guide || SHOW_STEP_PHOTOS) && tiles.length > 0;

  if (remoteError && !missing)
    return (
      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-10 text-center">
        <span className="text-[18px] text-mute">
          리포트를 불러오지 못했어요. {errorMessage(remoteError)}
        </span>
        <button type="button" onClick={remote.retry} className="text-[18px] font-bold text-navy">
          다시 시도
        </button>
      </main>
    );
  if (waiting)
    return (
      <main className="flex flex-1 flex-col items-center justify-center px-10 text-center">
        <span className="text-[18px] text-mute">리포트를 불러오고 있어요</span>
      </main>
    );
  if (!rep) return null;

  const remove = async () => {
    if (del === "busy") return;
    if (!account) {
      router.replace("/login");
      return;
    }
    setDel("busy");
    // 이미 지운 기록(404)도 지운 것으로 본다
    try {
      await deleteReport(rep.id);
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) {
        setDel("fail");
        return;
      }
    }
    update((prev) => ({ reports: prev.reports.filter((r) => r.id !== rep.id) }));
    router.replace("/my/reports");
  };

  return (
    <main className="relative flex min-h-0 flex-1 flex-col">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton
          size={44}
          onClick={() => router.push("/my/reports")}
          title="리포트 목록"
          aria-label="리포트 목록"
        />
        <span className="font-serif text-[28px] leading-none text-navy italic">Report</span>
        <span className="text-[17px] text-mute">메이크업 분석 리포트</span>
        <button
          type="button"
          onClick={() => setDel("ask")}
          className="ml-auto flex h-11 items-center rounded-full border-[1.5px] border-error/25 px-[18px] text-[16px] font-bold text-error hover:bg-ice-pale"
        >
          삭제
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-10 pt-7 pb-8">
        <div className="flex flex-col gap-1.5">
          <span className="text-[16px] text-mute">
            {rep.date} · {rep.steps}단계
          </span>
          <h1 className="font-display text-[34px] leading-[1.25] text-ink">{rep.title}</h1>
        </div>

        <div className="relative h-[480px] shrink-0 overflow-hidden rounded-3xl border border-line">
          {!hasFinal ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 bg-cream">
              <span className="font-display text-[26px] text-ink">미촬영</span>
              <span className="text-[17px] text-mute">
                {rep.noPhoto ? "사진 없이 완료한 메이크업이에요" : "완성 사진이 없어요"}
              </span>
            </div>
          ) : finalShot ? (
            <StepPhotoImg photo={finalShot} alt="완성 사진" />
          ) : rep.photoUrl ? (
            <img
              src={rep.photoUrl}
              alt="완성 사진"
              className="absolute inset-0 h-full w-full object-cover"
            />
          ) : rep.runId ? (
            <PhotoSlot label="사진을 불러오지 못했어요" />
          ) : rep.guide ? (
            <PhotoSlot label="마지막 단계 사진" />
          ) : (
            <PhotoSlot label="사진을 불러오지 못했어요" />
          )}
          <span className="absolute top-[18px] left-[18px] rounded-full bg-white px-[18px] py-2.5 font-label text-[15px] font-semibold tracking-[.14em] text-ink">
            FINAL LOOK
          </span>
        </div>

        {showSteps && (
          <section className="flex flex-col gap-3.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="flex items-baseline gap-2.5">
                <span className="font-serif text-[26px] leading-none text-ink italic">
                  Step captures
                </span>
                <span className="text-[16px] text-mute">스텝별 내 얼굴</span>
              </span>
              <button
                type="button"
                onClick={() => setExpanded((e) => !e)}
                className="text-[17px] font-semibold text-navy"
                aria-expanded={expanded}
              >
                {expanded ? "접기" : "펼쳐보기"}
              </button>
            </div>
            {expanded && (
              <div className="grid grid-cols-4 gap-2.5">
                {tiles.map((t) => (
                  <div key={t.no} className="flex flex-col gap-1.5">
                    <div className="relative aspect-square overflow-hidden rounded-[14px] border border-line">
                      <StepPhoto row={t.row} url={t.row.photoUrl} />
                      <span className="absolute top-2 left-2 rounded-full bg-white px-2 py-[3px] font-serif text-[18px] text-ink">
                        {t.no}
                      </span>
                    </div>
                    <span className="text-[16px] text-ink">{t.label}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="flex flex-col">
          <div className="flex items-baseline gap-2.5 pb-3">
            <span className="font-serif text-[26px] leading-none text-ink italic">Step guide</span>
            <span className="text-[16px] text-mute">순서 · 레퍼런스 제품 / 내가 쓴 제품</span>
          </div>
          {steps.map((c, i) => (
            <div key={c.no} className="flex flex-col">
              {heads.has(i) && (
                <span className="border-t border-line pt-4 pb-1 text-[16px] font-bold text-navy">
                  {heads.get(i)}
                </span>
              )}
              <div className="grid grid-cols-[40px_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)] items-start gap-3.5 border-t border-line py-3.5">
                <span className="font-serif text-[26px] leading-none text-navy">{c.no}</span>
                <span className="flex flex-col gap-1">
                  <span className="font-display text-[17px] text-ink">{c.title}</span>
                  <span className="text-[16px] leading-[1.45] text-mute">{c.guide}</span>
                </span>
                <span className="flex flex-col gap-[3px] text-[16px]">
                  <span className="text-mute">레퍼런스</span>
                  <span className="font-semibold text-ink">{c.ref}</span>
                </span>
                <span className="flex flex-col gap-[3px] text-[16px]">
                  <span className="text-mute">{c.usedKind}</span>
                  <span className="font-semibold text-ink">{c.used}</span>
                </span>
              </div>
            </div>
          ))}
        </section>
      </div>

      <Modal
        open={!!del}
        onClose={() => del !== "busy" && setDel(null)}
        className="flex max-w-[540px] flex-col gap-[22px] px-[30px] pt-[34px] pb-[26px]"
      >
        <div className="flex flex-col gap-2.5">
          <h2 className="font-display text-[30px] leading-[1.25] text-ink">
            {del === "fail"
              ? "삭제하지 못했어요"
              : del === "busy"
                ? "삭제 중…"
                : "이 리포트를 삭제할까요?"}
          </h2>
          <p className="text-[18px] leading-[1.55] text-mute">
            {del === "fail"
              ? "잠시 후 다시 시도해 주세요."
              : "단계 사진도 함께 삭제돼요. 삭제한 리포트는 되돌릴 수 없어요."}
          </p>
        </div>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => setDel(null)}
            disabled={del === "busy"}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[19px] font-bold text-ink disabled:opacity-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={() => void remove()}
            disabled={del === "busy"}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full bg-error text-[19px] font-bold text-white disabled:opacity-70"
          >
            {del === "fail" ? "다시 시도" : "삭제"}
          </button>
        </div>
      </Modal>
    </main>
  );
}
