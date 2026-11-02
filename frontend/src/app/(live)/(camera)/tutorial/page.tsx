"use client";

import { ArrowRight, Volume2, VolumeX, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { useHiddenVideo } from "@/features/face";
import {
  GuideOverlay,
  loadDefaultGuideSet,
  loadGuideArea,
  resolveStep,
  useStepInView,
  type AreaSubStep,
  type GuideArea,
  type GuideSet,
} from "@/features/guide";
import { LiveNote, RoundBack, parseAlert, useLiveState } from "@/features/live/live-chrome";
import { matchFor, useSession } from "@/features/session";
import { ActCard, PrepCard } from "@/features/tutorial/step-cards";
import { MOCK_GUIDE_AREA_URL } from "@/lib/mock-guide";
import { GUIDE_STEPS, REF_PRODUCTS, type GuideStepInfo } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { useSpeech } from "@/lib/use-speech";
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

/**
 * 10 튜토리얼 (GUIDE-003 · 006 · 007 · 008 · 011 · 013).
 * ?alert=cover 등은 측정 불가 상태 확인용.
 * 사진 저장에 동의했으면 단계를 넘길 때 확인 창 없이 사진을 남긴다 (동의는 튜토리얼 안내에서 받는다).
 * ponytail: 진하기 게이지는 목표값으로 서서히 차오르는 연출. GUIDE-013 측정이 생기면 gauge를 측정값으로 바꾼다.
 */
export default function TutorialPage() {
  const router = useRouter();
  const query = useQuery();
  const { state, update, updateRun, startRun } = useSession();
  const run = state.run;
  const alert = parseAlert(query?.get("alert"));

  const [defaults, setDefaults] = useState<GuideSet | null>(null);
  const [area, setArea] = useState<GuideArea | null>(null);
  const [step, setStep] = useState(0);
  // 지금 하는 동작. '했어요'로 하나씩 넘긴다
  const [act, setAct] = useState(0);
  // false면 단계 준비 카드(제품·할 일·끝내는 기준)를 띄운다. 앞으로 갈 때만 띄우고, 이전 단계로 돌아갈 때는 띄우지 않는다
  const [ready, setReady] = useState(false);
  const [gauge, setGauge] = useState(10);
  const [busy, setBusy] = useState(false);
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

  // 카메라는 추적에만 쓰고 영상은 보여 주지 않는다. 얼굴 자리에는 가이드만 뜬다
  useHiddenVideo();

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
  // 한 단계 안에서 영역이 바뀌어도 나눠 넘기지 않고 모든 영역을 한 번에 그린다
  const guideStep = useMemo(
    () => resolveStep(info.stepId, subs, defaults),
    [info.stepId, subs, defaults],
  );
  // 가까이 다가가 지금 단계 부위만 잘려도 화면 밖으로 잘린 것으로 안내하고 측정을 멈춘다
  const stepInView = useStepInView(guideStep);
  const { note, canRender, canMeasure } = useLiveState(alert, stepInView ? null : "out-of-frame");
  // 카메라 오류·준비 중·알림·얼굴 없음·거리 부족이면 측정 불가 (CAMERA-004 · GUIDE-013)
  const blocked = !canMeasure;

  useEffect(() => {
    if (!ready || blocked || busy || exitAsk || !hasProduct) return;
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
  }, [ready, blocked, busy, exitAsk, hasProduct, info.target]);

  const gv = Math.round(gauge);
  // 변수 이름을 그대로 적어야 Tailwind가 테마 변수를 CSS에 넣는다
  const meterColor = blocked
    ? "var(--color-ash)"
    : gv > 62
      ? "var(--color-rose)"
      : gv < 45
        ? "var(--color-sky)"
        : "var(--color-lime)";
  // 잴 수 없을 때는 이유를 위쪽 알림이 알려 주므로 판정 문구를 띄우지 않는다
  const gaugeLabel =
    gv > 62 ? "레퍼런스보다 진해요" : gv < 45 ? "레퍼런스보다 연해요" : "레퍼런스와 비슷해요";
  // 제품 없는 단계는 동작을 한꺼번에 보여 주고 바로 건너뛸 수 있다 (GUIDE-003)
  const lastAct = !hasProduct || act >= info.acts.length - 1;
  // 화면에 띄우고 읽어 줄 동작. AI 단계 설명에 동작이 비어 있으면 아무것도 띄우지 않는다
  const shownActs = hasProduct ? (info.acts[act] ? [act] : []) : info.acts.map((_, i) => i);

  // 진행바·이전 버튼으로 옮기면 촬영 대기 타이머는 버린다. 예전 step으로 advance가 실행되지 않게
  const cancelTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setBusy(false);
  };
  const goStep = (i: number, prep = true) => {
    cancelTimer();
    setStep(i);
    setAct(0);
    setReady(!prep);
    setGauge(10);
  };
  // 사진 저장에 동의했고 제품을 쓴 단계면 넘길 때 사진을 남긴다
  const photo = run.photoOk && hasProduct && !run.captures.includes(step);
  const advance = () => {
    if (photo) updateRun({ captures: [...run.captures, step] });
    if (last) router.push("/done");
    else goStep(step + 1);
  };
  const next = () => {
    if (busy) return;
    if (!lastAct) {
      setAct((a) => a + 1);
      return;
    }
    // 남길 사진이 없으면 '저장 중…' 없이 바로 넘긴다
    if (!photo) return advance();
    setBusy(true);
    timer.current = setTimeout(() => {
      setBusy(false);
      advance();
    }, 600);
  };
  const quit = () => {
    if (timer.current) clearTimeout(timer.current);
    startRun({});
    router.push("/home");
  };

  // 바르는 동안 화면을 읽기 어려우니, 켜 두면 준비 카드와 지금 할 동작을 읽어 준다
  const mine = pr.p;
  const speech = !ready
    ? [
        `${step + 1}단계, ${info.title}.`,
        mine ? `준비할 제품은 ${mine.brand} ${mine.name}.` : "내 파우치에 맞는 제품이 없어요.",
        `할 일은 ${info.acts.length}가지예요.`,
      ].join(" ")
    : shownActs
        .map((i) => {
          const a = info.acts[i];
          const tip = a.tip ? ` ${a.tip.kind === "caution" ? "주의" : "팁"}, ${a.tip.text}.` : "";
          const done = i === info.acts.length - 1 && info.doneWhen ? ` ${info.doneWhen}.` : "";
          return `${i + 1}. ${a.text}.${tip}${done}`;
        })
        .join(" ");
  useSpeech(state.voice ? speech : null);

  const nextLabel = busy
    ? "저장 중…"
    : !lastAct
      ? "했어요 · 다음 할 일"
      : last
        ? "완성하기"
        : hasProduct
          ? "다음 스텝"
          : "건너뛰기";

  return (
    <main className="relative flex flex-1 flex-col">
      {/* 가이드는 상단 바·제품 칩과 하단 안내 사이 빈 칸에만 그린다 */}
      <div className="relative mt-[140px] flex-1">
        {/* 이 단계에 그릴 가이드가 없어도 윤곽은 띄운다. 알림으로 가이드를 숨기는 동안은 윤곽도 숨긴다 */}
        <GuideOverlay step={canRender ? guideStep : null} fit face={canRender} />
      </div>

      {/* 준비 카드(z-[4])가 떠 있어도 나가기·음성 끄기를 누를 수 있게 그 위에 둔다 */}
      <div className="absolute inset-x-5 top-5 z-[5] flex items-center gap-3.5">
        <button
          type="button"
          onClick={() => {
            // 저장 대기 중에 나가기 창을 열면 뒤에서 단계가 넘어가지 않게 대기를 버린다
            cancelTimer();
            setExitAsk(true);
          }}
          className="flex h-12 shrink-0 items-center gap-2 rounded-full border border-white/15 bg-ink-deep/82 py-0 pr-[18px] pl-3 text-[16px] font-bold whitespace-nowrap text-white hover:bg-ink-deep/95"
        >
          <X className="size-[18px]" strokeWidth={2.4} aria-hidden />
          나가기
        </button>
        <button
          type="button"
          onClick={() => update({ voice: !state.voice })}
          aria-pressed={state.voice}
          aria-label={state.voice ? "음성 안내 끄기" : "음성 안내 켜기"}
          className={cn(
            "flex size-12 shrink-0 items-center justify-center rounded-full border border-white/15",
            state.voice ? "bg-white text-plum" : "bg-ink-deep/82 text-white",
          )}
        >
          {state.voice ? (
            <Volume2 className="size-[20px]" strokeWidth={2.2} aria-hidden />
          ) : (
            <VolumeX className="size-[20px]" strokeWidth={2.2} aria-hidden />
          )}
        </button>
        <div className="flex h-12 min-w-0 flex-1 items-center gap-3.5 rounded-full border border-white/15 bg-ink-deep/82 px-[18px]">
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
                onClick={() => goStep(i, i > step)}
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
      {/* 영상 속 제품 → 내 제품. 자세한 건 준비 카드에 있어 한 줄로 줄인다. 같은 자리에 알림이 뜨면 숨긴다 */}
      {!note && (
        <div className="absolute top-[84px] left-5 z-[2] flex h-11 max-w-[calc(100%-40px)] items-center gap-2 rounded-full bg-white/92 py-0 pr-4 pl-2 text-[14px] font-bold text-ink backdrop-blur-md">
          <span
            className="size-7 shrink-0 rounded-full border-2 border-white ring-1 ring-line"
            style={{ background: ref.color }}
            aria-label="영상 속 제품 색"
          />
          <span className="max-w-[200px] truncate text-mute">{ref.name}</span>
          <ArrowRight className="size-4 shrink-0 text-plum" strokeWidth={2.4} aria-hidden />
          {hasProduct ? (
            <>
              <span
                className="size-7 shrink-0 rounded-full border-2 border-white ring-1 ring-line"
                style={{ background: pr.p?.color ?? "#fff" }}
                aria-label="내 제품 색"
              />
              <span className="max-w-[200px] truncate">{pr.p?.name}</span>
            </>
          ) : (
            <span className="whitespace-nowrap text-plum">내 파우치에 없음</span>
          )}
        </div>
      )}
      <LiveNote note={note} />

      {/* 하단 안내는 상자 없이 띄워, 지금 할 일 한 줄과 얇은 게이지만 보여 준다 */}
      <div className="relative flex flex-col gap-3.5 px-7 pt-2 pb-[18px]">
        <div className="flex items-end gap-3">
          <span className="shrink-0 font-serif text-[34px] leading-[.9] text-rose italic tabular">
            {String(step + 1).padStart(2, "0")}
          </span>
          <h1 className="font-display text-[26px] leading-[1.15] text-white">{info.title}</h1>
          {hasProduct && info.acts.length > 1 && (
            <span className="shrink-0 text-[15px] text-line-2 tabular">
              할 일 {act + 1}/{info.acts.length}
            </span>
          )}
          {hasProduct && !blocked && (
            <span
              className="ml-auto shrink-0 text-[20px] leading-tight font-extrabold whitespace-nowrap transition-colors"
              style={{ color: meterColor }}
            >
              {gaugeLabel}
            </span>
          )}
        </div>
        {/* 지금 할 동작을 카드 한 장으로 크게, 다음 동작은 흐리게 미리 보여 준다. 제품 없는 단계는 동작 전부 */}
        <div className="flex flex-col gap-2">
          {shownActs.map((i) => (
            <ActCard
              key={info.acts[i].text}
              n={i + 1}
              act={info.acts[i]}
              doneWhen={i === info.acts.length - 1 ? info.doneWhen : null}
            />
          ))}
          {hasProduct && act < info.acts.length - 1 && (
            <span className="truncate px-2 text-[16px] text-ash">
              다음 {act + 2}. {info.acts[act + 1].text}
            </span>
          )}
        </div>

        {hasProduct && (
          <div className="flex items-center gap-3 text-[13px] font-semibold text-line-2">
            <span>연하게</span>
            <div className="relative h-2.5 flex-1">
              <div className="absolute inset-0 rounded-full bg-white/10" />
              <span
                className="absolute top-0 bottom-0 left-0 rounded-full transition-[width,background] duration-400"
                style={{ width: blocked ? "0%" : `${gv}%`, background: meterColor }}
              />
              {/* 레퍼런스 위치선. 어두운 게이지 위라 미러필름 모드에서도 흰색 그대로 둔다(data-dark) */}
              <span
                data-dark
                className="absolute -top-1.5 -bottom-1.5 left-[53.5%] -ml-[1.5px] w-[3px] rounded-sm bg-white"
              />
            </div>
            <span>진하게</span>
          </div>
        )}

        <div className="flex items-center gap-3">
          <RoundBack
            onClick={() => {
              // 저장 중에는 막는다. 대기 중인 advance가 바뀐 화면 위에서 이전 단계를 넘기지 않게
              if (busy) return;
              if (act > 0) return setAct((a) => a - 1);
              if (step > 0) goStep(step - 1, false);
            }}
            label={act > 0 ? "이전 할 일" : "이전 단계"}
            className={cn((busy || (step === 0 && act === 0)) && "opacity-35")}
          />
          <button
            type="button"
            onClick={next}
            disabled={busy}
            className="flex h-[72px] min-w-0 flex-1 items-center justify-between gap-4 rounded-full bg-pink py-0 pr-2.5 pl-[30px] text-white shadow-[0_12px_28px_color-mix(in_srgb,var(--color-pink)_38%,transparent)] active:scale-[.98] disabled:opacity-60"
          >
            <span className="truncate text-[22px] font-bold">{nextLabel}</span>
            <span className="flex size-[54px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
              <ArrowRight className="size-[26px]" strokeWidth={2.4} aria-hidden />
            </span>
          </button>
        </div>
      </div>

      {!ready && (
        <PrepCard
          step={step}
          info={info}
          refProduct={ref}
          match={pr}
          onStart={() => setReady(true)}
        />
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
