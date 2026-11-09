"use client";

import { Camera, Home } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { useRunQuery as useQuery } from "@/features/guide";
import { snapshotSteps, useSession, type ReportSummary } from "@/features/session";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { GUIDE_STEPS, VIDEOS, REF_PRODUCTS } from "@/mocks/mock-data";

type Save = "saving" | "saved" | "fail";

/**
 * 11 완성. 기록 저장 → 리포트 보기.
 * ?fail=1 은 저장 실패 상태 확인용. ponytail: 저장은 타이머. 서버 완료 기록이 붙으면 같은 실행 id로 재요청해 중복을 막는다.
 */
export default function DonePage() {
  const router = useRouter();
  const query = useQuery();
  const { state, update, endRun } = useSession();
  const run = state.run;
  const picked = run.picked ?? VIDEOS[0];
  const n = GUIDE_STEPS.length;
  // 최종 사진은 마지막 단계를 찍었을 때만. 중간 단계 사진은 따로 센다
  const hasFinal = run.photoOk && run.captures.includes(n - 1);
  const hasPhoto = run.photoOk && run.captures.length > 0;
  // 기록 id = 실행 id. 다시 시도해도 같은 기록을 덮어써 중복이 생기지 않는다.
  // 실행 id가 없는 예전 세션은 화면에 머무는 동안 한 번 만든 id를 쓴다
  const [fallbackId] = useState(() => `rp${Date.now()}`);
  const reportId = run.id ? `rp-${run.id}` : fallbackId;

  const [save, setSave] = useState<Save>("saving");
  const timer = useTimeout();

  // 저장 성공 시점에 기록을 만든다 (upsert). 리포트 보기 버튼은 이동만 한다
  // 타이머가 끝날 때의 최신 실행 상태(prev.run)로 기록한다. 렌더 시점 값을 붙잡지 않게
  const commit = () => {
    const d = new Date();
    update((prev) => {
      const r = prev.run;
      if (r.id !== run.id || r.mode === "guide") return {};
      const id = r.id ? `rp-${r.id}` : fallbackId;
      const video = r.picked ?? VIDEOS[0];
      const items = snapshotSteps(REF_PRODUCTS, r, prev.pouch);
      const report: ReportSummary = {
        id,
        title: video.title,
        date: `${d.getMonth() + 1}월 ${d.getDate()}일`,
        steps: n,
        subs: items.filter((s) => s.kind === "sub").length,
        isNew: true,
        noPhoto: !r.photoOk,
        finalPhoto: r.photoOk && r.captures.includes(n - 1),
        captures: r.photoOk ? [...r.captures] : [],
        videoId: video.id,
        items,
      };
      const rest = prev.reports.filter((x) => x.id !== id).map((r) => ({ ...r, isNew: false }));
      return { reports: [report, ...rest] };
    });
  };
  // 서버 저장을 흉내 낸다. 처음 한 번은 주소의 ?fail 로 실패를 만들 수 있다
  const runSave = (fail: boolean) => {
    setSave("saving");
    timer.set(() => {
      if (!fail) commit();
      setSave(fail ? "fail" : "saved");
    }, 1200);
  };
  useEffect(() => {
    if (!query) return;
    // 진입 때 한 번만 저장한다. 상태는 초기값이 saving이라 타이머만 건다
    const fail = query.get("fail") === "1";
    timer.set(() => {
      if (!fail) commit();
      setSave(fail ? "fail" : "saved");
    }, 1200);
    return timer.clear;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 진입 때 한 번만 저장한다
  }, [query]);

  const openReport = () => {
    if (save !== "saved") return;
    endRun(run.id);
    router.replace(`/my/report?id=${reportId}`);
  };

  return (
    <main className="flex min-h-dvh flex-1 flex-col gap-6 bg-white px-10 pt-9 pb-8 text-ink">
      <div className="flex flex-col gap-3">
        <span className="font-label text-[16px] font-semibold tracking-[.16em] text-navy">
          LOOK COMPLETE · {n} / {n}
        </span>
        <span className="font-serif text-[88px] leading-[.9] text-navy italic">
          Beautifully done.
        </span>
        <h1 className="font-display text-[26px] leading-[1.35] text-pretty">
          {picked.title} · 완성했어요
        </h1>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-3xl border border-line">
        {hasFinal ? (
          <>
            {/* TODO(GUIDE-010): 마지막 단계 촬영 결과 */}
            {/* eslint-disable-next-line @next/next/no-img-element -- 샘플 */}
            <img
              src="/images/sample-face.png"
              alt="완성 사진"
              className="absolute top-0 left-0 h-auto w-[187.9%] max-w-none"
              style={{ marginTop: "-92.7%" }}
            />
            <span className="absolute top-[18px] left-[18px] rounded-full bg-white px-[18px] py-2.5 font-label text-[15px] font-semibold tracking-[.14em]">
              FINAL · 마지막 단계 사진
            </span>
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-cream p-6 text-center">
            <span className="flex size-[72px] items-center justify-center rounded-full border-[2.5px] border-dashed border-ash text-navy">
              <Camera className="size-[30px]" strokeWidth={1.8} aria-hidden />
            </span>
            <span className="font-display text-[26px]">미촬영</span>
            <span className="text-[18px] text-mute">
              {hasPhoto
                ? "마지막 단계 사진이 없어요. 찍은 단계 사진은 리포트에 남아요."
                : "사진 없이 완료했어요. 사용한 제품은 리포트에 남아요."}
            </span>
          </div>
        )}
      </div>

      {save === "saving" && (
        <div className="flex items-center gap-3 rounded-[18px] bg-cream px-5 py-4" role="status">
          <span
            className="size-2.5 shrink-0 rounded-full bg-cyan"
            style={{ animation: "mr-pulse 1.4s ease-out infinite" }}
          />
          <span className="text-[19px] font-semibold">기록 저장 중…</span>
        </div>
      )}
      {save === "fail" && (
        <div
          className="flex items-center gap-4 rounded-[18px] border-[1.5px] border-cyan bg-ice-pale py-4 pr-4 pl-5"
          role="alert"
        >
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[19px] font-bold text-navy">기록을 저장하지 못했어요</span>
            <span className="text-[16px] text-mute">다시 시도해도 같은 기록으로 저장돼요.</span>
          </span>
          <button
            type="button"
            onClick={() => runSave(false)}
            className="flex h-14 shrink-0 items-center rounded-full bg-ice px-6 text-[18px] font-bold whitespace-nowrap text-ink"
          >
            다시 시도
          </button>
        </div>
      )}
      {save === "saved" && (
        <div className="flex items-center gap-3 rounded-[18px] bg-cream px-5 py-4" role="status">
          <span className="size-2.5 shrink-0 rounded-full bg-navy" />
          <span className="min-w-0 flex-1 text-[19px] font-semibold">기록을 저장했어요</span>
        </div>
      )}

      <div className="flex min-w-0 flex-col gap-1.5 px-1">
        <span className="font-label text-[15px] font-semibold tracking-[.14em] text-navy">
          출처
        </span>
        <span className="font-display text-[30px] leading-[1.25] text-pretty">{picked.title}</span>
        <span className="text-[19px] font-semibold text-mute">{picked.ch}</span>
      </div>

      <div className="-mx-10 -mb-8 flex items-center gap-3 border-t border-line px-10 pt-5 pb-7">
        <button
          type="button"
          onClick={() => {
            endRun(run.id);
            router.push("/home");
          }}
          aria-label="홈"
          className="flex size-20 shrink-0 items-center justify-center rounded-full border-2 border-line hover:bg-cream-2 active:scale-[.95]"
        >
          <Home className="size-7" strokeWidth={2} aria-hidden />
        </button>
        <PillButton
          size="hero"
          trailing
          onClick={openReport}
          disabled={save !== "saved"}
          className="min-w-0 flex-1 transition-opacity disabled:bg-ice disabled:opacity-45"
        >
          <span className="flex flex-col gap-0.5">
            <span className="whitespace-nowrap">리포트 보기</span>
            <span className="truncate text-[15px] font-medium text-navy">
              {hasPhoto ? "스텝별 사진 · 사용한 제품" : "사용한 제품 · 사진 없음"}
            </span>
          </span>
        </PillButton>
      </div>
    </main>
  );
}
