"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { pickOf } from "@/features/check";
import { useHiddenVideo } from "@/features/face";
import {
  checkGuideArea,
  TutorialViewport,
  loadDefaultGuideSet,
  loadGuideArea,
  resolveStep,
  toGuideArea,
  useGuide,
  useGuideTrackingIssue,
  useTutorialCrop,
  type GuideArea,
  type GuideModel,
  type GuideSet,
  type Makeup,
} from "@/features/guide";
import { useRunQuery as useQuery } from "@/features/guide";
import { LiveNote, parseAlert, RoundBack, useLiveState } from "@/features/live";
import {
  matchFor,
  runHref,
  useSession,
  type GuideAction,
  type RefProduct,
} from "@/features/session";
import {
  ActCard,
  DensityMeter,
  ExitModal,
  GuideStatus,
  PrepCard,
  ProductChip,
  templateOf,
  TutorialTopBar,
  type StepProduct,
} from "@/features/tutorial";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { GUIDE_STEPS, REF_PRODUCTS } from "@/mocks/mock-data";
import { MOCK_GUIDE_AREA_URL } from "@/mocks/mock-guide";

/** 튜토리얼 한 단계에 필요한 것. 샘플과 가이드 조회 응답을 같은 모양으로 맞춘다 */
interface TutorialStep {
  stepId: string;
  makeup: Makeup;
  short: string;
  title: string;
  acts: GuideAction[];
  doneWhen: string | null;
  /** 레퍼런스 진하기(0~100). 기준이 없으면 null이고 게이지를 띄우지 않는다 */
  target: number | null;
  product: StepProduct | null;
  /** 샘플 매칭용 제품. 가이드 조회 응답은 아직 내 파우치와 맞춰 보지 않아 null */
  ref: RefProduct | null;
}

const SAMPLE_STEPS: TutorialStep[] = GUIDE_STEPS.map((s, i) => {
  const r = REF_PRODUCTS[i];
  return {
    stepId: s.stepId,
    makeup: s.makeup,
    short: s.short,
    title: s.title,
    acts: s.acts,
    doneWhen: s.doneWhen,
    target: s.target,
    product: {
      name: r.name,
      full: `${r.brand} ${r.name}`,
      shade: r.shade,
      color: r.color,
      state: r.refState ?? null,
    },
    ref: r,
  };
});

/** 가이드 조회 응답의 단계. 동작이 비면 요약 한 줄을 동작처럼 보여 준다 */
function stepsOf(guide: GuideModel): TutorialStep[] {
  return guide.steps.map((s) => {
    const name = s.product?.name ?? s.product?.shade ?? null;
    return {
      stepId: s.stepId,
      makeup: s.makeup,
      short: s.label,
      title: s.label,
      acts: s.actions.length ? s.actions : s.summary ? [{ text: s.summary, tip: null }] : [],
      doneWhen: s.doneWhen,
      target: null,
      product: name
        ? {
            name,
            full: name,
            shade: s.product?.name ? s.product.shade : null,
            color: null,
            state: "unreg",
          }
        : null,
      ref: null,
    };
  });
}

/**
 * 10 튜토리얼.
 * ?guideId=승인된 가이드 ID 면 가이드 조회 API의 단계·설명·영역으로, 없으면 샘플 영상으로 돈다.
 * ?area=경로 는 샘플일 때만 다른 영역 파일을 본다. ?alert=cover 등은 측정 불가 상태 확인용.
 */
export default function TutorialPage() {
  const query = useQuery();
  const { state } = useSession();
  if (!query) return null;
  return state.run.mode === "guide" ? (
    <GuideTutorial />
  ) : (
    <SampleTutorial area={query.get("area")} />
  );
}

function SampleTutorial({ area: areaUrl }: { area: string | null }) {
  const [area, setArea] = useState<GuideArea | null>(null);
  useEffect(() => {
    loadGuideArea(areaUrl ?? MOCK_GUIDE_AREA_URL)
      .then(setArea)
      .catch((e) => console.warn("가이드 영역을 불러오지 못해 기본 가이드로 보여 줍니다", e));
  }, [areaUrl]);
  return <TutorialRun steps={SAMPLE_STEPS} area={area} />;
}

function GuideTutorial() {
  const router = useRouter();
  const { load, retry } = useGuide();
  const guide = load.status === "ready" ? load.guide : null;
  const steps = useMemo(() => (guide ? stepsOf(guide) : []), [guide]);
  const [area, setArea] = useState<GuideArea | null>(null);

  useEffect(() => {
    const raw = guide && toGuideArea(guide);
    if (!raw) return;
    let alive = true;
    // 영역을 쓸 수 없으면(지원하지 않는 메시 판 등) 설명과 기본 가이드로 진행한다
    checkGuideArea(raw, `guide ${guide.guideId}`)
      .then((checked) => alive && setArea(checked))
      .catch((e) => console.warn("가이드 영역을 쓸 수 없어 기본 가이드로 보여 줍니다", e));
    return () => {
      alive = false;
    };
  }, [guide]);

  const home = { label: "홈으로", onClick: () => router.push("/home") };
  switch (load.status) {
    case "loading":
      return <GuideStatus title="가이드를 불러오고 있어요" />;
    case "invalidId":
      return <GuideStatus title="가이드 주소가 올바르지 않아요" action={home} />;
    case "invalidated":
    case "notFound":
      return (
        <GuideStatus
          title="가이드가 없거나 아직 이용할 수 없어요"
          body="검수가 끝난 가이드만 따라 할 수 있어요."
          action={home}
        />
      );
    case "login":
      return (
        <GuideStatus
          title="로그인이 필요해요"
          action={{ label: "로그인하기", onClick: () => router.push("/login") }}
        />
      );
    case "error":
      return (
        <GuideStatus
          title="가이드를 불러오지 못했어요"
          body={load.message}
          action={{
            label: "다시 시도",
            onClick: () => {
              void retry();
            },
          }}
        />
      );
    case "ready":
      if (!steps.length)
        return <GuideStatus title="따라 할 단계가 없는 가이드예요" action={home} />;
      return <TutorialRun steps={steps} area={area} />;
  }
}

/**
 * 사진 저장에 동의했으면 단계를 넘길 때 확인 창 없이 사진을 남긴다 (동의는 튜토리얼 안내에서 받는다).
 * ponytail: 진하기 게이지는 목표값으로 서서히 차오르는 연출. 진하기 측정이 생기면 gauge를 측정값으로 바꾼다.
 */
function TutorialRun({ steps, area }: { steps: TutorialStep[]; area: GuideArea | null }) {
  const router = useRouter();
  const query = useQuery();
  const { state, updateRun, endRun, completeRun, isCurrentRun } = useSession();
  const { load } = useGuide();
  const run = state.run;
  const alert = parseAlert(query?.get("alert"));

  const [defaults, setDefaults] = useState<GuideSet | null>(null);
  const [step, setStep] = useState(0);
  // 지금 하는 동작. '했어요'로 하나씩 넘긴다
  const [act, setAct] = useState(0);
  // false면 단계 준비 카드(제품·할 일·끝내는 기준)를 띄운다. 앞으로 갈 때만 띄우고, 이전 단계로 돌아갈 때는 띄우지 않는다
  const [ready, setReady] = useState(false);
  const [gauge, setGauge] = useState(10);
  const [busy, setBusy] = useState(false);
  const [exitAsk, setExitAsk] = useState(false);
  const timer = useTimeout();

  useEffect(() => {
    loadDefaultGuideSet()
      .then(setDefaults)
      .catch((e) => console.warn("기본 가이드를 불러오지 못했습니다", e));
  }, []);

  // 카메라는 추적에만 쓰고 영상은 보여 주지 않는다. 얼굴 자리에는 가이드만 뜬다
  useHiddenVideo();

  const info = steps[step];
  // 샘플은 내 파우치와 맞춰 본다. 가이드 조회 응답은 아직 맞춰 보지 않아(제품 매칭 전) null
  const pr = info.ref ? matchFor(info.ref, run, state.pouch) : null;
  // 실제 가이드의 선택은 표시만 하고 촬영·게이지 판단에는 쓰지 않는다
  const pick = info.ref ? null : pickOf(info.stepId, run.choice, state.pouch);
  const hasProduct = !!pr && pr.kind !== "none";
  // 동작을 하나씩 넘기는지. 샘플에서 제품이 없는 단계만 동작을 한꺼번에 보여 주고 바로 건너뛸 수 있다
  const paced = hasProduct || !pr;
  // 진하기 기준이 있고 제품을 쓰는 단계만 게이지를 띄운다
  const target = hasProduct ? info.target : null;
  const last = step >= steps.length - 1;
  // 설명·제품과 얼굴 위 영역(GuideArea)은 단계 ID로 묶는다.
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
  // 가이드가 있는 단계는 지금 단계 부위의 판정(놓침·고개 돌림·잘림·너무 멂)으로 안내하고 측정을 멈춘다
  const { crop } = useTutorialCrop();
  const guideIssue = useGuideTrackingIssue(guideStep, crop);
  // 가이드가 없는 단계(해당 없음·실패)는 공통 얼굴 판정으로 안내하고 측정을 막는다
  const { note, canRender, canMeasure } = useLiveState(
    alert,
    null,
    guideStep ? { issue: guideIssue } : undefined,
  );
  // 카메라 오류·준비 중·알림·얼굴 없음·거리 부족이면 측정 불가
  const paused = run.mode === "guide" && (load.status !== "ready" || load.checking || !!load.error);
  const blocked = !canMeasure || paused;

  useEffect(() => {
    if (!ready || blocked || busy || exitAsk || target === null) return;
    const t = setInterval(() => {
      setGauge((g) => {
        if (g >= target) return g;
        return Math.min(
          target,
          g + Math.max(0.12, (target - g) * 0.02) * (0.6 + Math.random() * 0.8),
        );
      });
    }, 160);
    return () => clearInterval(t);
  }, [ready, blocked, busy, exitAsk, target]);

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
  const lastAct = !paced || act >= info.acts.length - 1;
  // 화면에 띄우고 읽어 줄 동작. 단계 설명에 동작이 비어 있으면 아무것도 띄우지 않는다
  const shownActs = paced ? (info.acts[act] ? [act] : []) : info.acts.map((_, i) => i);

  // 가이드를 다시 확인하는 동안 예약한 촬영을 취소한다
  useEffect(() => {
    if (!paused) return;
    timer.clear();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 재검증 중 예약 촬영을 취소한다
    setBusy(false);
  }, [paused, timer]);

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
  // 사진 저장에 동의했고 제품을 쓰는 단계면 넘길 때 사진을 남긴다. 실제 가이드는 건너뛴 단계만 뺀다
  const usesProduct = pick ? pick.kind !== "skipped" : hasProduct;
  const photo = run.photoOk && usesProduct && !run.captures.includes(info.stepId);
  const advance = () => {
    if (!isCurrentRun(run.id)) return;
    if (photo) updateRun({ captures: [...run.captures, info.stepId] }, run.id);
    if (last) {
      completeRun(run.id);
      router.push(runHref("/done", run.guideId));
    } else goStep(step + 1);
  };
  const next = () => {
    if (busy || paused) return;
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
    endRun(run.id);
    router.push("/home");
  };

  const nextLabel = busy
    ? "저장 중…"
    : !lastAct
      ? "했어요 · 다음 할 일"
      : last
        ? "완성하기"
        : paced
          ? "다음 스텝"
          : "건너뛰기";

  return (
    <main className="relative flex flex-1 flex-col">
      <TutorialViewport step={canRender ? guideStep : null} face={canRender} />
      <div className="flex-1" />

      <TutorialTopBar
        steps={steps}
        step={step}
        onExit={() => {
          // 저장 대기 중에 나가기 창을 열면 뒤에서 단계가 넘어가지 않게 대기를 버린다
          cancelTimer();
          setExitAsk(true);
        }}
        onGoStep={(i) => goStep(i, i > step)}
      />
      {/* 같은 자리에 알림이 뜨면 숨긴다 */}
      {/* 영상 제품 정보가 없어도 고른 제품이 있으면 보여 준다 */}
      {!note && (info.product || pick?.kind === "picked") && (
        <ProductChip
          refProduct={info.product}
          mine={hasProduct ? pr.p : null}
          pending={!pr}
          pick={pick}
        />
      )}
      <LiveNote note={note} />

      {/* 하단 안내는 상자 없이 띄워, 지금 할 일 한 줄과 얇은 게이지만 보여 준다 */}
      <div className="relative flex flex-col gap-3.5 px-7 pt-2 pb-[18px]">
        <div className="flex items-end gap-3">
          <span className="shrink-0 font-serif text-[34px] leading-[.9] text-blush italic tabular">
            {String(step + 1).padStart(2, "0")}
          </span>
          <h1 className="font-display text-[26px] leading-[1.15] text-white">{info.title}</h1>
          {paced && info.acts.length > 1 && (
            <span className="shrink-0 text-[15px] text-line-2 tabular">
              할 일 {act + 1}/{info.acts.length}
            </span>
          )}
          {target !== null && !blocked && (
            <span
              className="ml-auto shrink-0 text-[20px] leading-tight font-extrabold whitespace-nowrap transition-colors"
              style={{ color: meterColor }}
            >
              {gaugeLabel}
            </span>
          )}
        </div>
        {/* 지금 할 동작을 카드 한 장으로 크게, 다음 동작은 흐리게 미리 보여 준다. 제품 없는 샘플 단계는 동작 전부 */}
        <div className="flex flex-col gap-2">
          {shownActs.map((i) => (
            <ActCard
              key={info.acts[i].text}
              n={i + 1}
              act={info.acts[i]}
              doneWhen={i === info.acts.length - 1 ? info.doneWhen : null}
            />
          ))}
          {paced && act < info.acts.length - 1 && (
            <span className="truncate px-2 text-[16px] text-ash">
              다음 {act + 2}. {info.acts[act + 1].text}
            </span>
          )}
        </div>

        {target !== null && <DensityMeter value={gv} color={meterColor} blocked={blocked} />}

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
          total={steps.length}
          info={info}
          refProduct={info.product}
          match={pr}
          pick={pick}
          onStart={() => setReady(true)}
        />
      )}

      <ExitModal open={exitAsk} onQuit={quit} onClose={() => setExitAsk(false)} />
    </main>
  );
}
