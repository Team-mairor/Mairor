"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { mirrorScreen, useHiddenVideo } from "@/features/face";
import {
  GuideOverlay,
  loadDefaultGuideSet,
  loadGuideArea,
  resolveStep,
  useStepInView,
  type GuideArea,
  type GuideSet,
} from "@/features/guide";
import { LiveNote, parseAlert, RoundBack, useLiveState } from "@/features/live";
import { matchFor, useSession } from "@/features/session";
import {
  ActCard,
  DensityMeter,
  ExitModal,
  PrepCard,
  ProductChip,
  templateOf,
  TutorialTopBar,
} from "@/features/tutorial";
import { useQuery } from "@/lib/hooks/use-query";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { GUIDE_STEPS, REF_PRODUCTS } from "@/mocks/mock-data";
import { MOCK_GUIDE_AREA_URL } from "@/mocks/mock-guide";

/**
 * ponytail: 하프미러 얼굴 자리 정하기용 임시 표시(?layout=1). 위·아래 UI가 차지하는 칸과 가이드 칸을 테두리로,
 * 경계가 카메라에서 몇 mm 아래인지 함께 보여 준다. 자리가 정해지면 지운다
 */
function LayoutBoxes({
  guideRef,
  bottomRef,
}: {
  guideRef: RefObject<HTMLDivElement | null>;
  bottomRef: RefObject<HTMLDivElement | null>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<{
    guide: [number, number];
    bottom: number;
    h: number;
    toMm: (y: number) => number;
  } | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const g = guideRef.current?.getBoundingClientRect();
      const b = bottomRef.current?.getBoundingClientRect();
      if (!g || !b) return;
      const rect = el.getBoundingClientRect();
      const zoom = rect.width / el.clientWidth || 1;
      const y = (v: number) => (v - rect.top) / zoom;
      const s = mirrorScreen(el);
      setBox({
        guide: [y(g.top), y(g.bottom)],
        bottom: y(b.top),
        h: el.clientHeight,
        toMm: (v) => (v - s.originY) / s.pxPerMm,
      });
    };
    measure();
    // 하단 안내는 동작·단계마다 높이가 바뀐다
    const observer = new ResizeObserver(measure);
    if (bottomRef.current) observer.observe(bottomRef.current);
    observer.observe(el);
    return () => observer.disconnect();
  }, [guideRef, bottomRef]);

  const label = "absolute right-2 rounded bg-black px-1.5 text-[14px] font-bold tabular";
  return (
    <div ref={ref} className="pointer-events-none absolute inset-0 z-50">
      {box && (
        <>
          <div
            className="absolute inset-x-1 border-[3px] border-[#ff6b6b]"
            style={{ top: 0, height: box.guide[0] }}
          >
            <span className={`${label} bottom-1 text-[#ff6b6b]`}>
              위 UI 끝 {box.guide[0].toFixed(0)}px · 카메라 {box.toMm(box.guide[0]).toFixed(0)}mm
            </span>
          </div>
          <div
            className="absolute inset-x-1 border-[3px] border-dashed border-[#4ef0c2]"
            style={{ top: box.guide[0], height: box.guide[1] - box.guide[0] }}
          >
            <span className={`${label} top-1 text-[#4ef0c2]`}>
              가이드 칸 {box.toMm(box.guide[0]).toFixed(0)}~{box.toMm(box.guide[1]).toFixed(0)}mm
            </span>
          </div>
          <div
            className="absolute inset-x-1 border-[3px] border-[#5ce1ff]"
            style={{ top: box.bottom, height: box.h - box.bottom }}
          >
            <span className={`${label} top-1 text-[#5ce1ff]`}>
              아래 바 시작 {box.bottom.toFixed(0)}px · 카메라 {box.toMm(box.bottom).toFixed(0)}mm
            </span>
          </div>
        </>
      )}
    </div>
  );
}

/**
 * 10 튜토리얼 (GUIDE-003 · 006 · 007 · 008 · 011 · 013).
 * ?alert=cover 등은 측정 불가 상태 확인용.
 * 사진 저장에 동의했으면 단계를 넘길 때 확인 창 없이 사진을 남긴다 (동의는 튜토리얼 안내에서 받는다).
 * ponytail: 진하기 게이지는 목표값으로 서서히 차오르는 연출. GUIDE-013 측정이 생기면 gauge를 측정값으로 바꾼다.
 */
export default function TutorialPage() {
  const router = useRouter();
  const guideRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const query = useQuery();
  const { state, updateRun, startRun } = useSession();
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
  const timer = useTimeout();

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

  // 카메라는 추적에만 쓰고 영상은 보여 주지 않는다. 얼굴 자리에는 가이드만 뜬다
  useHiddenVideo();

  const info = GUIDE_STEPS[step];
  const ref = REF_PRODUCTS[step];
  const pr = matchFor(REF_PRODUCTS[step], run, state.pouch);
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
      ? "var(--color-blush)"
      : gv < 45
        ? "var(--color-sky)"
        : "var(--color-mint)";
  // 잴 수 없을 때는 이유를 위쪽 알림이 알려 주므로 판정 문구를 띄우지 않는다
  const gaugeLabel =
    gv > 62 ? "레퍼런스보다 진해요" : gv < 45 ? "레퍼런스보다 연해요" : "레퍼런스와 비슷해요";
  // 제품 없는 단계는 동작을 한꺼번에 보여 주고 바로 건너뛸 수 있다 (GUIDE-003)
  const lastAct = !hasProduct || act >= info.acts.length - 1;
  // 화면에 띄우고 읽어 줄 동작. AI 단계 설명에 동작이 비어 있으면 아무것도 띄우지 않는다
  const shownActs = hasProduct ? (info.acts[act] ? [act] : []) : info.acts.map((_, i) => i);

  // 진행바·이전 버튼으로 옮기면 촬영 대기 타이머는 버린다. 예전 step으로 advance가 실행되지 않게
  const cancelTimer = () => {
    timer.clear();
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
    timer.set(() => {
      setBusy(false);
      advance();
    }, 600);
  };
  const quit = () => {
    timer.clear();
    startRun({});
    router.push("/home");
  };

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
      {/*
        가이드는 상단 바·제품 칩과 하단 안내 사이에 그린다. 하단 안내 높이는 동작·단계마다 150px 가까이 달라서,
        남은 칸(flex-1)에 맞추면 '했어요'를 누를 때마다 얼굴 배율이 다시 잡혀 가이드가 출렁였다.
        그래서 하단 안내가 가장 클 때(약 370px)를 비워 둔 고정 칸에 그린다
      */}
      <div ref={guideRef} className="absolute inset-x-0 top-[140px] bottom-[372px]">
        {/* 이 단계에 그릴 가이드가 없어도 윤곽은 띄운다. 알림으로 가이드를 숨기는 동안은 윤곽도 숨긴다 */}
        <GuideOverlay step={canRender ? guideStep : null} fit face={canRender} />
      </div>
      <div className="flex-1" />

      <TutorialTopBar
        steps={GUIDE_STEPS}
        step={step}
        onExit={() => {
          // 저장 대기 중에 나가기 창을 열면 뒤에서 단계가 넘어가지 않게 대기를 버린다
          cancelTimer();
          setExitAsk(true);
        }}
        onGoStep={(i) => goStep(i, i > step)}
      />
      {/* 같은 자리에 알림이 뜨면 숨긴다 */}
      {!note && <ProductChip refProduct={ref} mine={hasProduct ? pr.p : null} />}
      <LiveNote note={note} />

      {/* 하단 안내는 상자 없이 띄워, 지금 할 일 한 줄과 얇은 게이지만 보여 준다 */}
      <div ref={bottomRef} className="relative flex flex-col gap-3.5 px-7 pt-2 pb-[18px]">
        <div className="flex items-end gap-3">
          <span className="shrink-0 font-serif text-[34px] leading-[.9] text-blush italic tabular">
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

        {hasProduct && <DensityMeter value={gv} color={meterColor} blocked={blocked} />}

        <div className="flex items-center gap-3">
          <RoundBack
            onClick={() => {
              // 저장 중에는 막는다. 대기 중인 advance가 바뀐 화면 위에서 이전 단계를 넘기지 않게
              if (busy) return;
              if (act > 0) return setAct((a) => a - 1);
              if (step > 0) goStep(step - 1, false);
            }}
            label={act > 0 ? "이전 할 일" : "이전 단계"}
            disabled={busy || (step === 0 && act === 0)}
          />
          <PillButton
            size="cta"
            trailing
            onClick={next}
            disabled={busy}
            className="min-w-0 flex-1 disabled:opacity-60"
          >
            {nextLabel}
          </PillButton>
        </div>
      </div>

      {!ready && (
        <PrepCard
          step={step}
          total={GUIDE_STEPS.length}
          info={info}
          refProduct={ref}
          match={pr}
          onStart={() => setReady(true)}
        />
      )}

      <ExitModal open={exitAsk} onQuit={quit} onClose={() => setExitAsk(false)} />
      {query?.has("layout") && <LayoutBoxes guideRef={guideRef} bottomRef={bottomRef} />}
    </main>
  );
}
