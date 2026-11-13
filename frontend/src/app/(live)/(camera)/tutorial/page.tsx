"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { pickOf } from "@/features/check";
import { useHiddenVideo, type RegionName } from "@/features/face";
import {
  categoryOfPart,
  checkGuideArea,
  groupIndexOf,
  groupSteps,
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
  type MatchCategory,
} from "@/features/guide";
import {
  abandonExecution,
  deleteFaceRegistration,
  uploadStepPhoto,
  useRunQuery as useQuery,
} from "@/features/guide";
import { LiveNote, parseAlert, RoundBack, useLiveState } from "@/features/live";
import {
  matchFor,
  runHref,
  saveStepPhoto,
  stepPhoto,
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
  reachableStep,
  TutorialTopBar,
  useStepShot,
  withStepTemplate,
  type StepProduct,
} from "@/features/tutorial";
import { ApiError, errorMessage } from "@/lib/api";
import { GUIDE_STEPS, REF_PRODUCTS } from "@/mocks/mock-data";
import { MOCK_GUIDE_AREA_URL } from "@/mocks/mock-guide";

/** 튜토리얼 한 단계에 필요한 것. 샘플과 가이드 조회 응답을 같은 모양으로 맞춘다 */
interface TutorialStep {
  stepId: string;
  makeup: Makeup;
  /** 상단 바에서 묶는 부위 */
  category: MatchCategory | null;
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
    category: categoryOfPart(s.makeup),
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
      category: s.matchCategory ?? categoryOfPart(s.makeup),
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

/** 단계의 가이드 영역 하위 단계. 영역에 없는 단계는 화장 종류의 기본 가이드를 쓴다 */
function subsOf(s: TutorialStep, area: GuideArea | null) {
  return withStepTemplate(
    area?.steps.find((a) => a.stepId === s.stepId)?.subSteps ?? [templateOf(s)],
    s.short,
  );
}

/** 영역을 찾지 못한 단계도 화장 종류의 기본 가이드 부위를 써, 립 단계에서 입이 보일 때 입술을 찍는다 */
function photoRegionsOf(s: TutorialStep, area: GuideArea | null, defaults: GuideSet | null) {
  const drawn = resolveStep(s.stepId, subsOf(s, area), defaults)?.regions ?? [];
  return drawn.length ? drawn : (resolveStep(s.stepId, [templateOf(s)], defaults)?.regions ?? []);
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
          body="분석이 끝나고 내려지지 않은 가이드만 따라 할 수 있어요."
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
 * 상단 바는 연속한 같은 부위 단계를 한 칸으로 묶고, 묶음의 마지막 단계를 넘길 때 확인 창 없이 사진을 한 장 남긴다.
 * 사진 저장 동의는 필수이고 튜토리얼 안내에서 받는다.
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
  const [exitAsk, setExitAsk] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  const countdownTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownActive = useRef(false);

  // 나가기로 실행을 끝낸 뒤에는 동의 카드로 보내지 않는다 (홈으로 가는 중)
  const leaving = useRef(false);
  // 동의 없이 들어오면(샘플 실행을 주소로 바로 연 경우 등) 사진을 찍지 않도록 동의 카드로 보낸다
  useEffect(() => {
    if (run.id && !run.photoOk && !leaving.current)
      router.replace(runHref("/tutorial/guide", run.guideId));
  }, [run.id, run.photoOk, run.guideId, router]);

  // 기본 가이드를 못 불러오면 영역 없는 단계는 찍을 부위를 몰라 촬영이 실패한다. 다시 찍기에서 다시 불러온다
  const [defaultsFailed, setDefaultsFailed] = useState(false);
  const loadDefaults = useCallback(() => {
    loadDefaultGuideSet()
      .then(setDefaults)
      .catch((e) => {
        console.warn("기본 가이드를 불러오지 못했습니다", e);
        setDefaultsFailed(true);
      });
  }, []);
  useEffect(loadDefaults, [loadDefaults]);

  // 카메라는 추적에만 쓰고 영상은 보여 주지 않는다. 얼굴 자리에는 가이드만 뜬다
  useHiddenVideo();

  const info = steps[step];
  const groups = useMemo(() => groupSteps(steps), [steps]);
  const g = groupIndexOf(groups, step);
  const group = groups[g];
  const groupLast = step === group.end - 1;
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
  // 설명·제품과 얼굴 위 영역(GuideArea)은 단계 ID로 묶는다. 그릴 것이 없으면 설명만 보여 준다
  const subs = useMemo(() => subsOf(info, area), [area, info]);
  // 한 단계 안에서 영역이 바뀌어도 나눠 넘기지 않고 모든 영역을 한 번에 그린다
  const guideStep = useMemo(
    () => resolveStep(info.stepId, subs, defaults),
    [info.stepId, subs, defaults],
  );
  // 묶음 사진을 기다리고 확대할 부위. 묶음 안 모든 단계의 부위를 합친다.
  // 실시간 안내·측정 판정은 그리는 가이드(guideStep) 기준이다
  const photoRegions = useMemo(
    () => [
      ...new Set<RegionName>(
        steps.slice(group.start, group.end).flatMap((s) => photoRegionsOf(s, area, defaults)),
      ),
    ],
    [steps, group.start, group.end, area, defaults],
  );
  // 촬영 기록이 아니라 실제로 남은 사진으로 상단 바의 이동 범위를 정한다. 사진은 묶음 마지막 단계에 있다
  const reachable = reachableStep(
    groups.map((x) => steps[x.end - 1].stepId),
    (id) => !!stepPhoto(run.id, id),
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

  // 실제 가이드는 단계 사진을 서버에 저장한 뒤 화면 상태를 확정하고 다음으로 간다.
  // 업로드에 실패하면 이전 사진과 단계 상태를 유지해 재시도할 수 있게 한다.
  const shot = useStepShot(photoRegions, async (photo) => {
    if (!isCurrentRun(run.id)) return;
    if (run.mode === "guide") {
      if (!run.executionId) throw new Error("실행 정보가 없습니다.");
      const image = await fetch(photo.url).then((response) => response.blob());
      try {
        await uploadStepPhoto(run.executionId, info.stepId, image);
      } catch (e) {
        // 동의가 없거나 철회됐으면 동의 카드에서 다시 받는다
        if (
          e instanceof ApiError &&
          e.code === "GUIDE_PHOTO_CONSENT_REQUIRED" &&
          isCurrentRun(run.id)
        )
          updateRun({ photoOk: false }, run.id);
        throw e;
      }
    }
    if (!isCurrentRun(run.id)) return;
    saveStepPhoto(run.id, info.stepId, photo);
    updateRun(
      (r) => (r.captures.includes(info.stepId) ? {} : { captures: [...r.captures, info.stepId] }),
      run.id,
    );
    if (last) {
      completeRun(run.id);
      router.push(runHref("/done", run.guideId));
    } else goStep(step + 1);
  });
  const { cancel: cancelShot } = shot;

  const cancelCountdown = () => {
    if (!countdownActive.current) return;
    countdownActive.current = false;
    if (countdownTimer.current !== null) {
      clearTimeout(countdownTimer.current);
      countdownTimer.current = null;
    }
    setCountdown(null);
  };

  const startFinalCountdown = () => {
    if (countdownActive.current) return;
    countdownActive.current = true;
    setCountdown(3);

    const tick = (remaining: number) => {
      countdownTimer.current = setTimeout(() => {
        if (!countdownActive.current) return;
        if (remaining > 1) {
          setCountdown(remaining - 1);
          tick(remaining - 1);
          return;
        }

        countdownActive.current = false;
        countdownTimer.current = null;
        setCountdown(null);
        shot.start();
      }, 1000);
    };

    tick(3);
  };

  useEffect(() => {
    if (!blocked && !paused && !exitAsk) return;
    countdownActive.current = false;
    if (countdownTimer.current !== null) {
      clearTimeout(countdownTimer.current);
      countdownTimer.current = null;
    }
    const resetTimer = setTimeout(() => setCountdown(null), 0);
    return () => clearTimeout(resetTimer);
  }, [blocked, paused, exitAsk]);

  useEffect(
    () => () => {
      countdownActive.current = false;
      if (countdownTimer.current !== null) clearTimeout(countdownTimer.current);
    },
    [],
  );

  useEffect(() => {
    if (!ready || blocked || exitAsk || target === null) return;
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
  }, [ready, blocked, exitAsk, target]);

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
  // 사진은 묶음 마지막 단계에서만 찍으므로, 촬영 부위를 다시 불러오는 것도 그 단계에서만 한다
  const reloadRegions = groupLast && defaultsFailed && photoRegions.length === 0;
  // 묶음 안 위치. 한 단계뿐인 묶음이면 띄우지 않는다
  const groupSize = group.end - group.start;
  const groupDetail =
    groupSize > 1 ? `${group.label} ${step - group.start + 1}/${groupSize}` : null;
  // 화면에 띄우고 읽어 줄 동작. 단계 설명에 동작이 비어 있으면 아무것도 띄우지 않는다
  const shownActs = paced ? (info.acts[act] ? [act] : []) : info.acts.map((_, i) => i);

  // 가이드를 다시 확인하는 동안 촬영 대기를 접는다
  useEffect(() => {
    if (paused) cancelShot();
  }, [paused, cancelShot]);

  // 진행바·이전 버튼으로 옮기면 촬영 대기를 접는다. 예전 단계 사진으로 넘어가지 않게
  function goStep(i: number, prep = true) {
    cancelCountdown();
    cancelShot();
    setStep(i);
    setAct(0);
    setReady(!prep);
    setGauge(10);
  }
  // 모든 묶음(제품 없는 단계·생략한 단계 포함)의 끝에서 사진을 찍는다. 못 찍으면 넘기지 않고 다시 찍게 한다
  const next = () => {
    if (countdownActive.current) return cancelCountdown();
    if (shot.shooting || shot.saving || paused) return;
    if (!lastAct) {
      setAct((a) => a + 1);
      return;
    }
    if (!groupLast) return goStep(step + 1);
    if (reloadRegions) {
      setDefaultsFailed(false);
      return loadDefaults();
    }
    if (last) startFinalCountdown();
    else shot.start();
  };
  const quit = () => {
    leaving.current = true;
    cancelCountdown();
    cancelShot();
    // 실제 가이드는 서버 실행을 중도 종료한다. 실패해도 서버가 세션 종료 때 정리하므로 기다리지 않는다
    if (run.mode === "guide" && run.executionId)
      abandonExecution(run.executionId).catch((e: unknown) => console.warn("중도 종료 실패", e));
    else if (run.mode === "guide" && run.faceRegistrationId)
      deleteFaceRegistration(run.faceRegistrationId).catch((e: unknown) =>
        console.warn("얼굴 등록 정리 실패", e),
      );
    endRun(run.id);
    router.push("/home");
  };

  const nextLabel =
    countdown !== null
      ? "촬영 취소"
      : shot.state === "outOfView"
        ? "화면에 보이면 찍어요"
        : shot.state === "waiting"
          ? "잠시 멈춰 주세요…"
          : lastAct && reloadRegions
            ? "다시 불러오기"
            : shot.state === "failed"
              ? "다시 찍기"
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

      {countdown !== null && (
        <div
          className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-night/55 px-8 text-center text-white"
          role="status"
          aria-live="assertive"
          aria-label={`마지막 사진 촬영까지 ${countdown}초`}
        >
          <span className="font-serif text-[clamp(120px,30vw,220px)] leading-none tabular-nums">
            {countdown}
          </span>
          <span className="text-[21px] font-bold">잠시 후 마지막 사진을 촬영해요</span>
          <span className="text-[16px] text-white/80">
            아래 버튼을 누르면 촬영을 취소할 수 있어요
          </span>
        </div>
      )}

      <TutorialTopBar
        groups={groups}
        group={g}
        onExit={() => {
          // 촬영을 기다리는 중에 나가기 창을 열면 뒤에서 단계가 넘어가지 않게 대기를 접는다
          cancelCountdown();
          cancelShot();
          setExitAsk(true);
        }}
        reachable={shot.saving ? -1 : reachable}
        onGoGroup={(i) => !shot.saving && i <= reachable && goStep(groups[i].start, i > g)}
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
            {String(g + 1).padStart(2, "0")}
          </span>
          <h1 className="font-display text-[26px] leading-[1.15] text-white">{info.title}</h1>
          {groupDetail && (
            <span className="shrink-0 text-[15px] text-line-2 tabular">{groupDetail}</span>
          )}
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

        {shot.state === "outOfView" && (
          <p
            role="status"
            className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-ink"
          >
            이 단계 부위가 화면에 다 보이게 조금 뒤로 가 주세요. 촬영을 그만두려면 왼쪽 버튼을 눌러
            주세요.
          </p>
        )}
        {shot.saving && (
          <p
            role="status"
            className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-ink"
          >
            사진을 저장하고 있어요. 잠시만 기다려 주세요.
          </p>
        )}
        {reloadRegions && (
          <p
            role="alert"
            className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-error"
          >
            촬영할 부위 정보를 불러오지 못했어요. 인터넷 연결을 확인한 뒤 다시 불러와 주세요.
          </p>
        )}
        {shot.state === "failed" && !reloadRegions && (
          <p
            role="alert"
            className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-error"
          >
            {shot.error
              ? `사진을 저장하지 못했어요. ${errorMessage(shot.error)} 다시 찍어 주세요.`
              : "사진을 저장하지 못했어요. 카메라가 켜져 있고 얼굴이 화면에 보이는지 확인한 뒤 다시 찍어 주세요."}
          </p>
        )}

        <div className="flex items-center gap-3">
          <RoundBack
            onClick={() => {
              if (countdownActive.current) return cancelCountdown();
              if (shot.saving) return;
              // 촬영을 기다리는 중이면(부위가 계속 화면 밖 등) 대기만 접고 지금 단계에 머문다
              if (shot.shooting) return cancelShot();
              if (act > 0) {
                // 마지막 할 일에서 촬영에 실패한 채 돌아가면 실패 안내·다시 찍기 라벨을 지운다
                cancelShot();
                return setAct((a) => a - 1);
              }
              if (step > 0) goStep(step - 1, false);
            }}
            label={
              shot.saving
                ? "저장 중…"
                : shot.shooting
                  ? "촬영 취소"
                  : act > 0
                    ? "이전 할 일"
                    : "이전 단계"
            }
            disabled={shot.saving || (!shot.shooting && step === 0 && act === 0)}
          />
          <PillButton
            size="cta"
            trailing
            onClick={next}
            disabled={shot.saving}
            className="min-w-0 flex-1"
          >
            {shot.saving ? "저장 중…" : nextLabel}
          </PillButton>
        </div>
      </div>

      {!ready && (
        <PrepCard
          step={g}
          total={groups.length}
          detail={groupDetail ?? undefined}
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
