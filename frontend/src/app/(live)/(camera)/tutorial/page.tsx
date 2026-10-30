"use client";

import { ArrowRight, Check, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import {
  GuideOverlay,
  loadDefaultGuideSet,
  loadGuideArea,
  resolveSubStep,
  useStepInView,
  type AreaSubStep,
  type GuideArea,
  type GuideSet,
} from "@/features/guide";
import {
  GlassPanel,
  LiveNote,
  RoundBack,
  parseAlert,
  useLiveState,
  type LiveReason,
} from "@/features/live/live-chrome";
import { matchFor, useSession } from "@/features/session";
import { MOCK_GUIDE_AREA_URL } from "@/lib/mock-guide";
import { GUIDE_STEPS, REF_PRODUCTS, type GuideStepInfo } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

/** 영역 데이터에 없는 단계는 화장 종류의 기본 가이드로 그린다 */
function templateOf(info: GuideStepInfo): AreaSubStep {
  return {
    subStepId: `${info.stepId}-1`,
    order: 1,
    status: "template",
    reasons: [],
    templateId: info.makeup,
    guideSets: [],
  };
}

/** 측정 불가 이유 (게이지 아래 한 줄) */
const BLOCK_WHY: Record<LiveReason, string> = {
  lost: "얼굴이 화면을 벗어났어요",
  turn: "고개를 정면으로 돌려 주세요",
  cover: "손이나 도구를 잠깐 내려 주세요",
  far: "조금 더 가까이 와 주세요",
  turned: "고개를 정면으로 돌려 주세요",
  "out-of-frame": "얼굴 전체가 보이게 해 주세요",
  light: "조명이 바뀌었어요",
  error: "카메라를 켤 수 없어요",
  starting: "카메라를 켜는 중이에요",
};
const SHEET_OK = {
  fail: false,
  title: "이 단계 사진을 저장했어요",
  desc: "리포트에 이 단계의 얼굴이 남아요.",
};
const SHEET_FAIL = {
  fail: true,
  title: "사진을 저장하지 못했어요",
  desc: "다시 찍거나, 사진 없이 다음 단계로 넘어갈 수 있어요.",
};

/**
 * 10 튜토리얼 (GUIDE-003 · 006 · 007 · 008 · 011 · 013).
 * ?alert=cover 등은 측정 불가 상태 확인용, ?photofail=1 은 촬영 실패 상태 확인용.
 * ponytail: 진하기 게이지는 목표값으로 서서히 차오르는 연출. GUIDE-013 측정이 생기면 gauge를 측정값으로 바꾼다.
 */
export default function TutorialPage() {
  const router = useRouter();
  const query = useQuery();
  const { state, updateRun, startRun } = useSession();
  const run = state.run;
  const alert = parseAlert(query?.get("alert"));

  const [defaults, setDefaults] = useState<GuideSet | null>(null);
  const [area, setArea] = useState<GuideArea | null>(null);
  const [step, setStep] = useState(0);
  const [subIdx, setSubIdx] = useState(0);
  const [gauge, setGauge] = useState(10);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState<typeof SHEET_OK | null>(null);
  const [exitAsk, setExitAsk] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // API 연동 전까지는 목업 가이드와 같은 샘플 영상의 가이드 영역을 쓰고, ?area=경로 로 다른 파일을 본다.
  useEffect(() => {
    if (!query) return;
    loadDefaultGuideSet()
      .then(setDefaults)
      .catch((e) => console.warn("기본 가이드를 불러오지 못했습니다", e));
    loadGuideArea(query.get("area") ?? MOCK_GUIDE_AREA_URL)
      .then(setArea)
      .catch((e) => console.warn("가이드 영역을 불러오지 못해 기본 가이드로 보여 줍니다", e));
  }, [query]);
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  const info = GUIDE_STEPS[step];
  const ref = REF_PRODUCTS[step];
  const pr = matchFor(step, run, state.pouch);
  const hasProduct = pr.kind !== "none";
  const last = step >= GUIDE_STEPS.length - 1;
  // 설명·제품(GUIDE_STEPS)과 얼굴 위 영역(GuideArea)은 단계 ID로 묶는다.
  // 영역에 없는 단계는 화장 종류의 기본 가이드를 쓰고, 그릴 것이 없으면 설명만 보여 준다
  const subs = useMemo(
    () => area?.steps.find((s) => s.stepId === info.stepId)?.subSteps ?? [templateOf(info)],
    [area, info],
  );
  // 한 단계 안에서 영역이 바뀌면 하위 단계를 차례로 보여 준다. 게이지와 단계 사진은 단계마다 한 번이다
  const sub = subs[Math.min(subIdx, subs.length - 1)];
  const lastSub = subIdx >= subs.length - 1;
  const guideStep = useMemo(() => resolveSubStep(sub, defaults), [sub, defaults]);
  // 기본 가이드를 쓰는 하위 단계만 기본 가이드를 불러올 때까지 기다린다
  const descOnly = guideStep == null && (sub.status !== "template" || defaults != null);
  // 가까이 다가가 지금 단계 부위만 잘려도 화면 밖으로 잘린 것으로 안내하고 측정을 멈춘다
  const stepInView = useStepInView(guideStep);
  const { note, canRender, canMeasure, reason } = useLiveState(
    alert,
    stepInView ? null : "out-of-frame",
  );
  // 카메라 오류·준비 중·알림·얼굴 없음·거리 부족이면 측정 불가 (CAMERA-004 · GUIDE-013)
  const blocked = !canMeasure;

  useEffect(() => {
    if (sheet || blocked || busy || exitAsk || !hasProduct) return;
    const t = setInterval(() => {
      setGauge((g) => {
        if (g >= info.target) return g;
        return Math.min(
          info.target,
          g + Math.max(0.12, (info.target - g) * 0.02) * (0.6 + Math.random() * 0.8),
        );
      });
    }, 160);
    return () => clearInterval(t);
  }, [sheet, blocked, busy, exitAsk, hasProduct, info.target]);

  const gv = Math.round(gauge);
  const meterColor = blocked ? "#C9B5BF" : gv > 62 ? "#FF8FC0" : gv < 45 ? "#EFC0DA" : "#DBE586";
  const gaugeLabel = blocked
    ? "지금은 잴 수 없어요"
    : gv > 62
      ? "레퍼런스보다 진해요"
      : gv < 45
        ? "레퍼런스보다 연해요"
        : "레퍼런스와 비슷해요";
  const meterHint = blocked
    ? BLOCK_WHY[reason ?? "lost"]
    : gv > 62
      ? "경계를 블렌딩해 주세요"
      : gv < 45
        ? "한 번 더 얹어 주세요"
        : "지금 딱 좋아요";
  const actIdx = !hasProduct ? -1 : gv >= 45 ? 1 : 0;

  // 진행바·이전 버튼으로 옮기면 촬영 대기 타이머는 버린다. 예전 step으로 advance가 실행되지 않게
  const cancelTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setBusy(false);
  };
  const goStep = (i: number) => {
    cancelTimer();
    setStep(i);
    setSubIdx(0);
    setGauge(10);
    setSheet(null);
  };
  const advance = (noPhoto: boolean) => {
    const skip = noPhoto || !!sheet?.fail;
    const captures = skip || run.captures.includes(step) ? run.captures : [...run.captures, step];
    updateRun({ captures });
    setSheet(null);
    if (last) router.push("/done");
    else goStep(step + 1);
  };
  const next = () => {
    if (busy || sheet) return;
    if (!lastSub) {
      setSubIdx((k) => k + 1);
      return;
    }
    setBusy(true);
    timer.current = setTimeout(() => {
      setBusy(false);
      if (!run.photoOk || !hasProduct) advance(true);
      else setSheet(query?.get("photofail") === "1" ? SHEET_FAIL : SHEET_OK);
    }, 600);
  };
  const quit = () => {
    if (timer.current) clearTimeout(timer.current);
    startRun({});
    router.push("/home");
  };

  const nextLabel = busy
    ? run.photoOk && hasProduct
      ? "사진 찍는 중…"
      : "저장 중…"
    : !lastSub
      ? `다음 영역 · ${subIdx + 2}/${subs.length}`
      : last
        ? "완성하기"
        : hasProduct
          ? "다음 스텝"
          : "건너뛰기";

  return (
    <main className="relative flex flex-1 flex-col">
      <GuideOverlay step={canRender ? guideStep : null} />

      <div className="absolute inset-x-5 top-5 z-[2] flex items-center gap-3.5">
        <button
          type="button"
          onClick={() => setExitAsk(true)}
          className="flex h-12 shrink-0 items-center gap-2 rounded-full border border-white/15 bg-[rgba(42,10,28,.82)] py-0 pr-[18px] pl-3 text-[16px] font-bold whitespace-nowrap text-white hover:bg-[rgba(42,10,28,.95)]"
        >
          <X className="size-[18px]" strokeWidth={2.4} aria-hidden />
          나가기
        </button>
        <div className="flex h-12 min-w-0 flex-1 items-center gap-3.5 rounded-full border border-white/15 bg-[rgba(42,10,28,.82)] px-[18px]">
          <div
            className="flex min-w-0 flex-1 gap-1"
            role="progressbar"
            aria-valuenow={step + 1}
            aria-valuemax={GUIDE_STEPS.length}
          >
            {GUIDE_STEPS.map((s, i) => (
              <button
                key={s.stepId}
                type="button"
                onClick={() => goStep(i)}
                aria-label={`${i + 1}단계 ${s.short}`}
                className={cn(
                  "h-1.5 flex-1 rounded-full transition-colors",
                  i < step ? "bg-plum" : i === step ? "bg-pink" : "bg-line-2",
                )}
              />
            ))}
          </div>
          <span className="font-serif text-[24px] leading-none whitespace-nowrap text-white tabular">
            {step + 1} / {GUIDE_STEPS.length}
          </span>
        </div>
      </div>
      <LiveNote note={note} />

      <GlassPanel>
        <div className="absolute top-0 left-5 flex h-[60px] max-w-[calc(100%-40px)] -translate-y-[calc(100%+12px)] items-center gap-3 rounded-full bg-white/92 py-0 pr-5 pl-2.5 text-ink shadow-[0_10px_24px_rgba(20,4,12,.28)] backdrop-blur-md">
          <span
            className="size-10 shrink-0 rounded-full border-[3px] border-white shadow-[0_0_0_1px_#EFE4EA]"
            style={{ background: ref.color }}
          />
          <span className="flex min-w-0 flex-col">
            <span className="text-[12px] font-semibold whitespace-nowrap text-mute">
              영상 속 제품
            </span>
            <span className="max-w-[220px] truncate text-[15px] font-bold">
              {ref.brand} {ref.name}
            </span>
          </span>
          <ArrowRight className="size-[18px] shrink-0 text-plum" strokeWidth={2.4} aria-hidden />
          {hasProduct ? (
            <>
              <span
                className="size-10 shrink-0 rounded-full border-[3px] border-white shadow-[0_0_0_1px_#EFE4EA]"
                style={{ background: pr.p?.color ?? "#fff" }}
              />
              <span className="flex min-w-0 flex-col">
                <span className="text-[12px] font-semibold whitespace-nowrap text-plum">
                  {pr.kind === "same" ? "내 파우치 · 같은 제품" : "내 파우치 · 대체 제품"}
                </span>
                <span className="max-w-[220px] truncate text-[15px] font-bold">
                  {pr.p?.brand} {pr.p?.name}
                </span>
              </span>
            </>
          ) : (
            <>
              <span className="size-10 shrink-0 rounded-full border-[2.5px] border-dashed border-ash" />
              <span className="flex min-w-0 flex-col">
                <span className="text-[12px] font-semibold whitespace-nowrap text-mute">
                  내 파우치
                </span>
                <span className="text-[15px] font-bold whitespace-nowrap text-plum">
                  해당 제품 없음
                </span>
              </span>
            </>
          )}
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-baseline gap-3.5">
            <span className="shrink-0 font-serif text-[44px] leading-[.9] text-rose italic tabular">
              {String(step + 1).padStart(2, "0")}
            </span>
            <h1 className="font-display text-[30px] leading-[1.15] text-white">{info.title}</h1>
            {subs.length > 1 && (
              <span className="ml-auto shrink-0 text-[17px] text-line-2 tabular">
                영역 {subIdx + 1}/{subs.length}
              </span>
            )}
          </div>
          {descOnly ? (
            <span className="text-[17px] leading-[1.5] text-line-2">
              {sub.status === "failed"
                ? "영상에서 바를 곳을 찾지 못해 설명으로만 진행해요"
                : "이 단계는 얼굴 위 가이드 없이 설명으로만 진행해요"}
            </span>
          ) : (
            guideStep?.source === "template" && (
              <span className="text-[17px] leading-[1.5] text-rose">
                영상에서 위치를 찾지 못해 기본 위치로 보여 드려요
              </span>
            )
          )}
        </div>

        <div className="-mt-1 flex flex-col gap-2.5">
          {info.acts.map((t, i) => {
            const on = actIdx < 0 || i === actIdx;
            const done = actIdx >= 0 && i < actIdx;
            return (
              <div
                key={t}
                className={cn(
                  "flex min-h-[52px] items-center gap-3.5 rounded-[18px] py-0 pr-[18px] pl-2.5 transition-colors",
                  on && actIdx >= 0 && "bg-white/10",
                )}
              >
                <span
                  className={cn(
                    "flex size-[34px] shrink-0 items-center justify-center rounded-full text-[17px] font-extrabold tabular",
                    on
                      ? "bg-pink text-white"
                      : done
                        ? "bg-white/90 text-plum"
                        : "bg-white/14 text-line-2",
                  )}
                >
                  {i + 1}
                </span>
                <span
                  className={cn(
                    "text-[23px] leading-[1.3] font-bold tracking-[-.01em]",
                    on ? "text-white" : "text-ash",
                  )}
                >
                  {t}
                </span>
              </div>
            );
          })}
        </div>

        {hasProduct && (
          <div className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between gap-4">
              <span
                className="text-[28px] font-extrabold whitespace-nowrap transition-colors"
                style={{ color: meterColor }}
              >
                {gaugeLabel}
              </span>
              <span className="text-[17px] whitespace-nowrap text-line-2">{meterHint}</span>
            </div>
            <div className="relative h-[18px]">
              <div className="absolute inset-0 rounded-full bg-white/10" />
              <span
                className="absolute top-0 bottom-0 left-0 rounded-full transition-[width,background] duration-400"
                style={{ width: blocked ? "0%" : `${gv}%`, background: meterColor }}
              />
              <span className="absolute -top-1.5 -bottom-1.5 left-[53.5%] -ml-[1.5px] w-[3px] rounded-sm bg-white" />
            </div>
            <div className="relative h-[18px] text-[14px] font-semibold text-line-2">
              <span className="absolute left-0">연하게</span>
              <span className="absolute left-[53.5%] -translate-x-1/2 whitespace-nowrap text-white">
                레퍼런스
              </span>
              <span className="absolute right-0">진하게</span>
            </div>
          </div>
        )}

        <div className="flex items-center gap-3">
          <RoundBack
            onClick={() => {
              if (subIdx === 0) return step > 0 && goStep(step - 1);
              cancelTimer();
              setSheet(null);
              setSubIdx((k) => k - 1);
            }}
            label={subIdx > 0 ? "이전 영역" : "이전 단계"}
            className={cn(step === 0 && subIdx === 0 && "opacity-35")}
          />
          <button
            type="button"
            onClick={next}
            disabled={busy}
            className="flex h-[72px] min-w-0 flex-1 items-center justify-between gap-4 rounded-full bg-pink py-0 pr-2.5 pl-[30px] text-white shadow-[0_12px_28px_rgba(219,19,116,.38)] active:scale-[.98] disabled:opacity-60"
          >
            <span className="truncate text-[22px] font-bold">{nextLabel}</span>
            <span className="flex size-[54px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
              <ArrowRight className="size-[26px]" strokeWidth={2.4} aria-hidden />
            </span>
          </button>
        </div>
      </GlassPanel>

      {/* 사진 확인 (GUIDE-008) */}
      {sheet && (
        <div
          className="absolute inset-0 z-[4] flex animate-fade items-center justify-center bg-[rgba(40,10,26,.58)] px-[60px] py-8 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
        >
          <div className="flex w-full max-w-[560px] flex-col gap-6 rounded-[36px] bg-white px-4 pt-4 pb-6 text-ink shadow-[0_40px_80px_rgba(20,4,12,.4)]">
            <div className="relative h-[300px] overflow-hidden rounded-3xl bg-ink-deep">
              {/* TODO(GUIDE-008): 실제 촬영 결과 */}
              {/* eslint-disable-next-line @next/next/no-img-element -- 샘플 */}
              <img
                src="/images/sample-face.png"
                alt=""
                className="absolute top-0 left-0 h-auto w-[187.9%] max-w-none"
                style={{ marginTop: "-112%" }}
              />
              <span className="absolute top-3.5 left-3.5 flex h-8 items-center gap-1.5 rounded-full bg-[rgba(42,10,28,.82)] px-3.5 text-[14px] font-bold text-white">
                <Check className="size-3.5" strokeWidth={3} aria-hidden />
                {sheet.fail ? "저장 실패" : "사진 저장됨"}
              </span>
            </div>
            <div className="flex flex-col items-center gap-2 px-4 text-center">
              <span className="font-label text-[14px] font-semibold tracking-[.14em] text-mute">
                STEP {String(step + 1).padStart(2, "0")} 사진
              </span>
              <h2
                className={cn(
                  "font-display text-[34px] leading-[1.2]",
                  sheet.fail ? "text-plum" : "text-ink",
                )}
              >
                {sheet.title}
              </h2>
              <p className="text-[18px] leading-[1.5] text-pretty">{sheet.desc}</p>
            </div>
            <div className="flex gap-2.5 px-2">
              <button
                type="button"
                onClick={() => setSheet(SHEET_OK)}
                className="flex h-20 shrink-0 items-center justify-center rounded-full border-2 border-line px-[30px] text-[21px] font-bold whitespace-nowrap active:scale-[.96]"
              >
                다시 찍기
              </button>
              <button
                type="button"
                onClick={() => advance(false)}
                className="flex h-20 min-w-0 flex-1 items-center justify-between gap-6 rounded-full bg-pink py-0 pr-2.5 pl-8 text-white shadow-[0_14px_30px_rgba(219,19,116,.26)] active:scale-[.97]"
              >
                <span className="truncate text-[23px] font-bold">
                  {sheet.fail ? "사진 없이 진행" : last ? "완성하기" : "다음 스텝"}
                </span>
                <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                  <ArrowRight className="size-7" strokeWidth={2.4} aria-hidden />
                </span>
              </button>
            </div>
          </div>
        </div>
      )}

      <Modal
        open={exitAsk}
        onClose={() => setExitAsk(false)}
        className="flex flex-col gap-7 rounded-[32px] px-9 pt-10 pb-8 text-ink"
      >
        <div className="flex flex-col gap-3">
          <h2 className="font-display text-[34px] leading-[1.25]">튜토리얼을 종료할까요?</h2>
          <p className="text-[19px] leading-[1.55] text-pretty text-mute">
            완료하지 않으면 기록과 사진이 남지 않아요.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={quit}
            className="flex h-[72px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[20px] font-bold hover:bg-cream"
          >
            종료
          </button>
          <button
            type="button"
            onClick={() => setExitAsk(false)}
            className="flex h-[72px] flex-1 items-center justify-center rounded-full bg-pink text-[20px] font-bold text-white active:scale-[.98]"
          >
            계속하기
          </button>
        </div>
      </Modal>
    </main>
  );
}
