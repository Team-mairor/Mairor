"use client";

import { ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { pickOf } from "@/features/check";
import { type RegionName } from "@/features/face";
import {
  GaugeDebug,
  productRule,
  substituteReference,
  useGaugeBaseline,
  useGaugeMeasure,
  type GaugeLabel,
  type SelectedProduct,
} from "@/features/gauge";
import {
  categoryOfPart,
  checkGuideArea,
  groupIndexOf,
  groupSteps,
  productStepKey,
  TutorialViewport,
  loadDefaultGuideSet,
  resolveStep,
  stepGauge,
  toGuideArea,
  useBrowFit,
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
  getExecution,
  uploadStepPhoto,
  useRunQuery as useQuery,
} from "@/features/guide";
import { LiveNote, parseAlert, RoundBack, useLiveState } from "@/features/live";
import {
  matchFor,
  runHref,
  saveStepPhoto,
  type StepPhoto,
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
  TutorialTopBar,
  useStepShot,
  type StepProduct,
  SelfiePreview,
  StepList,
} from "@/features/tutorial";
import { ApiError, errorMessage } from "@/lib/api";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { isMirror, subscribeMirror } from "@/lib/mirror";
import { cn } from "@/lib/utils";

/** 튜토리얼 한 단계에 필요한 실제 가이드 조회 응답 */
interface TutorialStep {
  stepId: string;
  makeup: Makeup;
  /** 상단 바에서 묶는 부위 */
  category: MatchCategory | null;
  short: string;
  title: string;
  acts: GuideAction[];
  doneWhen: string | null;
  product: StepProduct | null;
  /** 샘플 매칭용 제품. 가이드 조회 응답은 아직 내 파우치와 맞춰 보지 않아 null */
  ref: RefProduct | null;
}

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
  return area?.steps.find((a) => a.stepId === s.stepId)?.subSteps ?? [templateOf(s)];
}

/** 영역을 찾지 못한 단계도 화장 종류의 기본 가이드 부위를 써, 립 단계에서 입이 보일 때 입술을 찍는다 */
function photoRegionsOf(s: TutorialStep, area: GuideArea | null, defaults: GuideSet | null) {
  const drawn = resolveStep(s.stepId, subsOf(s, area), defaults, s.makeup)?.regions ?? [];
  return drawn.length
    ? drawn
    : (resolveStep(s.stepId, [templateOf(s)], defaults, s.makeup)?.regions ?? []);
}

/**
 * 10 튜토리얼.
 * 승인된 가이드 조회 API가 제공하는 단계·설명·영역으로 실행한다.
 */
export default function TutorialPage() {
  const query = useQuery();
  const { state } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (state.run.mode !== "guide") router.replace("/select");
  }, [router, state.run.mode]);
  if (!query) return null;
  return state.run.mode === "guide" ? <GuideTutorial /> : null;
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

const LABEL_TEXT: Record<GaugeLabel, string> = {
  lighter: "레퍼런스보다 연해요",
  similar: "레퍼런스와 비슷해요",
  darker: "레퍼런스보다 진해요",
};
const LABEL_COLOR: Record<GaugeLabel, string> = {
  lighter: "#20DFFF",
  similar: "#2EF58C",
  darker: "#FF3E9D",
};
const GAUGE_DEBUG_KEY = "mairor:gauge-debug";
const subscribeGaugeDebug = () => () => {};
const readGaugeDebug = () => sessionStorage.getItem(GAUGE_DEBUG_KEY) === "1";

/** 묶음 안 다음 단계로 넘어갈 때 단계 제목 · 할 일(제품이 바뀌면 제품도)을 강조하는 시간(ms) */
const ENTER_FLASH_MS = 1800;

interface EnteredStep {
  step: number;
  product: string | null;
  changed: boolean;
}

function enteredStepNotice({ product, changed }: EnteredStep) {
  if (changed) return product ? `제품을 바꿔 주세요 · ${product}` : "이 단계는 제품 없이 해요";
  return product ? "같은 제품으로 이어서 발라요" : "다음 단계예요";
}

/**
 * 게이지에 쓸 고른 제품. 실행 정보를 못 받으면(모의 실행 · 조회 실패) 제품 체크에서 건너뛴 단계만 숨기고
 * 같은 제품으로 본다
 */
function selectedProduct(
  products: Record<string, SelectedProduct> | null,
  stepId: string,
  skipped: boolean,
): SelectedProduct {
  return products?.[stepId] ?? { result: skipped ? "NONE" : "SAME", selectedColor: null, skipped };
}

/** 실행 시작 때 서버가 확정한 단계별 제품 선택. 못 받으면 null이고 제품 체크 선택으로 대신한다 */
function useExecutionProducts(executionId: string | null) {
  const [products, setProducts] = useState<Record<string, SelectedProduct> | null>(null);
  useEffect(() => {
    if (!executionId) return;
    let live = true;
    getExecution(executionId)
      .then((execution) => {
        if (!live) return;
        setProducts(
          Object.fromEntries(
            execution.steps.map((s) => [
              s.stepId,
              {
                result: s.result,
                selectedColor: s.selectedColor,
                skipped: s.skipped,
              },
            ]),
          ),
        );
      })
      .catch((e) =>
        console.warn("실행의 제품 선택을 불러오지 못해 게이지는 제품 체크 선택으로 정합니다", e),
      );
    return () => {
      live = false;
    };
  }, [executionId]);
  return products;
}

/**
 * 상단 바는 연속한 같은 제품 단계를 한 칸으로 묶고, 묶음의 마지막 단계를 넘길 때 확인 창 없이 사진을 한 장 남긴다.
 * 단계 목록에서 아무 묶음으로나 가고, 원하는 단계까지만 하고 지금 단계에서 완성할 수 있다.
 * 사진 저장 동의는 필수이고 튜토리얼 안내에서 받는다.
 * 진하기 게이지는 카메라에서 잰 이번 단계 화장 효과를 레퍼런스와 견준 값이다(features/gauge).
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
  // false면 단계 준비 카드(제품·할 일·끝내는 기준)를 띄운다. 앞으로 갈 때만 띄우고, 이전 단계로 돌아갈 때는 띄우지 않는다
  const [ready, setReady] = useState(false);
  const [exitAsk, setExitAsk] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  // 할 일 카드를 펼쳐 둘지. 설명이 길면 얼굴을 가려 접을 수 있게 하고, 다음 단계로 가도 고른 상태를 둔다
  const [actsOpen, setActsOpen] = useState(true);
  // 목록에서 지금 단계에서 완성하기를 골랐는지. 마지막 단계처럼 얼굴 전체 사진을 찍고 끝낸다
  const [finishing, setFinishing] = useState(false);
  const [countdown, setCountdown] = useState<number | null>(null);
  // 미러필름에서 마지막 사진 전에 카메라 화면을 띄우고 자세를 맞추는 중인지
  const [posing, setPosing] = useState(false);
  const [review, setReview] = useState<StepPhoto | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewError, setReviewError] = useState<unknown>(null);
  const countdownTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownActive = useRef(false);
  // 준비 카드 없이 들어온 묶음 안 단계. 잠깐 제목 · 할 일을 강조하고, 앞 단계와 제품이 다르면 제품도 띄운다
  const [entered, setEntered] = useState<EnteredStep | null>(null);
  const enteredTimer = useTimeout();

  // 나가기로 실행을 끝낸 뒤에는 동의 카드로 보내지 않는다 (홈으로 가는 중)
  const leaving = useRef(false);
  // 사진 촬영 동의가 없으면 촬영하지 않도록 동의 카드로 보낸다
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

  const info = steps[step];
  // 섀도 사이에 애교살·아이라인이 끼지 않게, 같은 제품으로 같은 동작을 이어 바를 때만 묶는다
  const groups = useMemo(() => groupSteps(steps, productStepKey), [steps]);
  const g = groupIndexOf(groups, step);
  const group = groups[g];
  const groupLast = step === group.end - 1;
  // 샘플은 내 파우치와 맞춰 본다. 가이드 조회 응답은 아직 맞춰 보지 않아(제품 매칭 전) null
  const pr = info.ref ? matchFor(info.ref, run, state.pouch) : null;
  // 실제 가이드의 선택은 표시만 하고 촬영·게이지 판단에는 쓰지 않는다
  const pick = info.ref ? null : pickOf(info.stepId, run.choice, state.pouch);
  const hasProduct = !!pr && pr.kind !== "none";
  // 바르는 단계인지. 샘플에서 제품이 없는 단계만 바로 건너뛸 수 있다
  const paced = hasProduct || !pr;
  const last = step >= steps.length - 1 || finishing;
  // 설명·제품과 얼굴 위 영역(GuideArea)은 단계 ID로 묶는다. 그릴 것이 없으면 설명만 보여 준다
  const subs = useMemo(() => subsOf(info, area), [area, info]);
  // 레퍼런스 게이지 기준이 있는 단계만 게이지를 띄우고, 고른 제품에 따라 숨기거나 색감을 뺀다
  const reference = useMemo(() => stepGauge(subs), [subs]);
  const products = useExecutionProducts(run.executionId);
  const skipped = pick?.kind === "skipped";
  const product = useMemo(
    () => selectedProduct(products, info.stepId, skipped),
    [products, info.stepId, skipped],
  );
  const rule = useMemo(
    () => (reference ? productRule(reference.gauge, info.makeup, product) : null),
    [reference, info.makeup, product],
  );
  // 대체 제품 색이 레퍼런스와 멀면 그 제품 색 쪽으로 옮긴 기준으로 잰다
  const measureGauge = useMemo(() => {
    const hex = product.selectedColor?.hex;
    if (!reference || rule?.basis !== "product" || !hex) return reference?.gauge ?? null;
    return substituteReference(reference.gauge, hex);
  }, [reference, rule?.basis, product]);
  const showGauge = !!rule?.show;
  const measured = useMemo(
    () => subs.find((sub) => sub.subStepId === reference?.subStepId)?.guideSets ?? [],
    [subs, reference?.subStepId],
  );
  const madeSets = useMemo(() => subs.flatMap((sub) => sub.guideSets), [subs]);
  // 한 단계 안에서 영역이 바뀌어도 나눠 넘기지 않고 모든 영역을 한 번에 그린다
  const resolved = useMemo(
    () => resolveStep(info.stepId, subs, defaults, info.makeup),
    [info.stepId, info.makeup, subs, defaults],
  );
  // 눈썹은 등록 사진의 원래 눈썹 모양·앞머리·꼬리에 맞춘다
  const guideStep = useBrowFit(resolved, run.id);
  const paused = run.mode === "guide" && (load.status !== "ready" || load.checking || !!load.error);
  // 묶음 안 다음 단계가 게이지를 띄우면 그 단계 시작 기준이 필요하다
  const nextInfo = groupLast ? null : steps[step + 1];
  const nextSkipped =
    !!nextInfo && pickOf(nextInfo.stepId, run.choice, state.pouch).kind === "skipped";
  const nextNeedsBaseline = useMemo(() => {
    if (!nextInfo) return false;
    const ref = stepGauge(subsOf(nextInfo, area));
    const chosen = selectedProduct(products, nextInfo.stepId, nextSkipped);
    return !!ref && productRule(ref.gauge, nextInfo.makeup, chosen).show;
  }, [nextInfo, area, products, nextSkipped]);
  const baselineKey = `${run.id}:${step}`;
  const [skippedBaselineKey, setSkippedBaselineKey] = useState<string | null>(null);
  const baselineSkipped = skippedBaselineKey === baselineKey;
  const gaugeActive = ready && showGauge && !baselineSkipped && !exitAsk && !paused;
  // 첫 단계에서 눈 화장 전 맨얼굴·흰자를 확보하고, 게이지 단계에서는 바르기 전 해당 부위를 다시 모은다.
  const baselineNeeded = step === 0 || showGauge;
  // 게이지가 이번 단계 화장만 재도록 단계 준비 카드가 떠 있는 동안 바르기 전 얼굴을 모은다.
  // 묶음 안 다음 단계는 카드 없이 시작하므로 이번 단계 동안 사진을 남겨 두었다가 그 단계 기준으로 쓴다
  const baseline = useGaugeBaseline({
    runId: run.id,
    step,
    collecting: !ready && baselineNeeded,
    makeup: info.makeup,
    regions: guideStep?.regions,
    recording: ready && nextNeedsBaseline && !paused,
    measuring: gaugeActive,
  });
  const stepBaseline = baseline.stepBaseline(step);
  const cameraTuning = !ready && baselineNeeded && !stepBaseline && baseline.status.lock === null;
  const [stalledAt, setStalledAt] = useState<{ key: string; frames: number } | null>(null);
  const [baselineEscapeKey, setBaselineEscapeKey] = useState<string | null>(null);
  useEffect(() => {
    if (ready || !baselineNeeded || stepBaseline || baseline.status.lock === null) return;
    const frames = baseline.status.frames;
    const timer = setTimeout(() => setStalledAt({ key: baselineKey, frames }), 1000);
    return () => clearTimeout(timer);
  }, [
    ready,
    baselineNeeded,
    stepBaseline,
    baseline.status.frames,
    baseline.status.lock,
    baselineKey,
  ]);
  useEffect(() => {
    if (ready || !baselineNeeded || stepBaseline) return;
    const timer = setTimeout(() => setBaselineEscapeKey(baselineKey), 8000);
    return () => clearTimeout(timer);
  }, [ready, baselineNeeded, stepBaseline, baselineKey]);
  const baselineStalled =
    !cameraTuning &&
    !ready &&
    baselineNeeded &&
    !stepBaseline &&
    stalledAt?.key === baselineKey &&
    stalledAt.frames === baseline.status.frames;
  const canSkipBaseline = baselineEscapeKey === baselineKey;
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
  // 가이드가 있는 단계는 지금 단계 부위의 판정(놓침·고개 돌림·잘림·너무 멂)으로 안내하고 측정을 멈춘다
  const { crop } = useTutorialCrop();
  // 미러필름은 크롭 없이 그리므로 판정도 크롭 없이 한다
  const mirror = useSyncExternalStore(subscribeMirror, isMirror, () => false);
  const guideIssue = useGuideTrackingIssue(guideStep, mirror ? null : crop);
  // 가이드가 없는 단계(해당 없음·실패)는 공통 얼굴 판정으로 안내하고 측정을 막는다
  const { note, canRender, canMeasure, reason } = useLiveState(
    alert,
    null,
    guideStep ? { issue: guideIssue } : undefined,
  );
  // 카메라 오류·준비 중·알림·얼굴 없음·거리 부족이면 측정 불가
  const blocked = !canMeasure || paused;

  // 실제 가이드는 단계 사진을 서버에 저장한 뒤 화면 상태를 확정하고 다음으로 간다.
  // 업로드에 실패하면 이전 사진과 단계 상태를 유지해 재시도할 수 있게 한다.
  const savePhoto = async (photo: StepPhoto) => {
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
    // 저장한 순서로 둔다. 완료 화면은 마지막으로 찍은 단계 사진을 완성 사진으로 쓴다
    updateRun(
      (r) => ({ captures: [...r.captures.filter((id) => id !== info.stepId), info.stepId] }),
      run.id,
    );
    if (last) {
      completeRun(run.id);
      router.push(runHref("/done", run.guideId));
    } else goStep(step + 1);
  };
  // 마지막 사진은 리포트 대표 사진이라 얼굴 전체가 보일 때 찍고, 저장 전에 다시 찍을 수 있게 한다
  const shot = useStepShot(
    photoRegions,
    async (photo) => {
      if (!last) return savePhoto(photo);
      setReviewError(null);
      setReview(photo);
    },
    last,
  );
  const confirmReview = async () => {
    if (!review || reviewSaving) return;
    setReviewSaving(true);
    setReviewError(null);
    try {
      await savePhoto(review);
    } catch (e) {
      setReviewError(e);
    } finally {
      setReviewSaving(false);
    }
  };
  const retake = () => {
    if (reviewSaving) return;
    setReview(null);
    setReviewError(null);
  };
  const { cancel: cancelShot } = shot;
  const selfie = mirror && last && (posing || countdown !== null || shot.shooting || shot.saving);

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

  // 개발 도구에서 ?gauge를 한 번 붙이면 같은 탭의 화면 이동 뒤에도 디버그 값을 계속 띄운다
  const gaugeDebugRequested = process.env.DEV_TOOLS === "1" && !!query?.has("gauge");
  const gaugeDebugStored = useSyncExternalStore(subscribeGaugeDebug, readGaugeDebug, () => false);
  useEffect(() => {
    if (process.env.DEV_TOOLS !== "1") return;
    if (gaugeDebugRequested) sessionStorage.setItem(GAUGE_DEBUG_KEY, "1");
  }, [gaugeDebugRequested]);
  const gaugeDebug = gaugeDebugRequested || gaugeDebugStored;
  const gaugeMeasure = useGaugeMeasure({
    // 먼 얼굴은 색이 부정확하므로 마지막 값을 유지하고, 가까워도 해당 부위가 보이면 계속 잰다
    active: gaugeActive && reason !== "far",
    // 기준이 대체 제품 쪽으로 바뀌면 다듬던 값을 이어 쓰지 않는다
    key: reference ? `${run.id}:${reference.subStepId}:${rule?.basis}` : null,
    makeup: info.makeup,
    gauge: measureGauge,
    guideSets: measured,
    madeSets,
    start: stepBaseline,
    white: baseline.status.white,
    debug: gaugeDebug,
    onShot: baseline.record,
  });
  const { display } = gaugeMeasure;
  const gaugeUnavailable =
    display?.reason === "thinArea" ||
    display?.reason === "weakReference" ||
    display?.reason === "noReference" ||
    display?.reason === "noWhite";
  const visibleGauge = showGauge && !baselineSkipped && !gaugeUnavailable;
  // 이전 화면에서 기준 없이 시작한 실행도 준비 카드를 다시 열어 같은 단계 기준을 모은다
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 기준이 없는 기존 실행을 준비 카드로 복구한다
    if (ready && showGauge && !baselineSkipped && display?.reason === "noBaseline") setReady(false);
  }, [ready, showGauge, baselineSkipped, display?.reason]);
  const gaugeLabel = display?.label ?? null;
  const meterBlocked = paused || reason === "far" || display?.bar == null;
  const meterColor = !gaugeLabel ? "#20DFFF" : LABEL_COLOR[gaugeLabel];
  const meterText = meterBlocked
    ? reason === "far"
      ? "조금 가까이 와 주세요"
      : display?.bar == null
        ? "화장을 바르면 내 위치가 움직여요"
        : "측정을 잠시 멈췄어요"
    : gaugeLabel
      ? LABEL_TEXT[gaugeLabel]
      : null;
  // 사진은 묶음 마지막 단계(또는 완성하는 단계)에서만 찍으므로, 촬영 부위를 다시 불러오는 것도 그때만 한다
  const reloadRegions = (groupLast || finishing) && defaultsFailed && photoRegions.length === 0;
  // 묶음 안 위치. 한 단계뿐인 묶음이면 띄우지 않는다
  const groupSize = group.end - group.start;
  const groupDetail =
    groupSize > 1 ? `${group.label} ${step - group.start + 1}/${groupSize}` : null;
  // 묶음 첫 카드에는 몇 단계로 나눠 바르는지만 알린다. 카드 없이 이어지는 단계는 들어갈 때 강조한다
  const prepDetail =
    groupSize > 1 && step === group.start
      ? `${group.label} · ${groupSize}단계로 나눠 발라요`
      : groupDetail;
  const flash = entered?.step === step ? entered : null;
  // 한 단계의 가이드 영역은 하나라 동작을 하나씩 넘기지 않고 한 번에 띄우고 읽어 준다
  const shownActs = info.acts.map((_, i) => i);

  // 가이드를 다시 확인하는 동안 촬영 대기를 접는다
  useEffect(() => {
    if (paused) cancelShot();
  }, [paused, cancelShot]);

  // 진행바·이전 버튼으로 옮기면 촬영 대기를 접는다. 예전 단계 사진으로 넘어가지 않게
  function goStep(i: number, prep = true) {
    cancelCountdown();
    cancelShot();
    setPosing(false);
    setReview(null);
    setReviewError(null);
    setStep(i);
    setReady(!prep);
    setEntered(null);
    setFinishing(false);
    setListOpen(false);
  }
  const openList = () => {
    // 촬영을 기다리는 중에 목록을 열면 뒤에서 단계가 넘어가지 않게 대기를 접는다
    cancelCountdown();
    cancelShot();
    setPosing(false);
    setListOpen(true);
  };
  // 목록에서 고른 묶음의 첫 단계로 간다. 바르기 전 얼굴로 게이지 기준을 잡도록 준비 카드부터 띄운다.
  // 지금 묶음을 고르면 완성하기를 거두고 이어서 한다
  const goGroup = (i: number) => {
    if (i !== g) return goStep(groups[i].start);
    setFinishing(false);
    setListOpen(false);
  };
  // 지금 단계의 할 일을 다 한 것으로 보고, 다음 버튼을 완성하기로 바꾼다
  const finishHere = () => {
    setListOpen(false);
    setFinishing(true);
    setReady(true);
  };
  /** 단계에서 쓸 내 제품 이름. 제품 없이 하면 null */
  const productNameOf = (s: TutorialStep) => {
    const picked = pickOf(s.stepId, run.choice, state.pouch);
    if (picked.kind === "skipped") return null;
    const matched = s.ref ? matchFor(s.ref, run, state.pouch).p : null;
    const item = picked.kind === "picked" ? picked.item : matched;
    return item ? `${item.brand} ${item.name}` : null;
  };
  // 묶음 안 다음 단계는 준비 카드 없이 시작한다. 게이지 기준을 앞 단계 사진으로 못 잡으면 그 단계만 카드에서 모은다
  const enterNextInGroup = () => {
    const nextStep = step + 1;
    const needsCard = nextNeedsBaseline && !baseline.takeNext(nextStep, steps[nextStep].makeup);
    goStep(nextStep, needsCard);
    if (needsCard) return;
    const before = productNameOf(info);
    const after = productNameOf(steps[nextStep]);
    setEntered({ step: nextStep, product: after, changed: after !== before });
    enteredTimer.set(() => setEntered(null), ENTER_FLASH_MS);
  };
  // 모든 묶음(제품 없는 단계·생략한 단계 포함)의 끝에서 사진을 찍는다. 못 찍으면 넘기지 않고 다시 찍게 한다
  const next = () => {
    if (countdownActive.current) return cancelCountdown();
    if (shot.shooting || shot.saving || paused) return;
    if (!groupLast && !finishing) return enterNextInGroup();
    if (reloadRegions) {
      setDefaultsFailed(false);
      return loadDefaults();
    }
    if (!last) return shot.start();
    // 미러필름은 카메라 화면을 먼저 띄우고, 자세를 맞춘 뒤 한 번 더 눌러야 카운트다운을 시작한다
    if (mirror && !posing) return setPosing(true);
    startFinalCountdown();
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
          : selfie && shot.state === "idle"
            ? "촬영하기"
            : reloadRegions
              ? "다시 불러오기"
              : shot.state === "failed"
                ? "다시 찍기"
                : last
                  ? "완성하기"
                  : paced
                    ? "다음 스텝"
                    : "건너뛰기";

  return (
    <main className="relative flex flex-1 flex-col">
      <TutorialViewport step={canRender && !selfie ? guideStep : null} />
      {!selfie && <div className="flex-1" />}

      {countdown !== null && !selfie && (
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
          setPosing(false);
          setExitAsk(true);
        }}
        listDisabled={shot.saving || reviewSaving}
        onList={openList}
      />
      {/* 같은 자리에 알림이 뜨면 숨긴다 */}
      {/* 영상 제품 정보가 없어도 고른 제품이 있으면 보여 준다 */}
      {!note && !selfie && (info.product || pick?.kind === "picked") && (
        <ProductChip
          refProduct={info.product}
          mine={hasProduct ? pr.p : null}
          pending={!pr}
          pick={pick}
        />
      )}
      {/* 셀카 화면에서는 카메라 오류·켜는 중 안내만 띄운다 */}
      <LiveNote note={selfie && reason !== "error" && reason !== "starting" ? null : note} />

      {/* 밝은 카메라 영상 위에서도 제목과 할 일이 읽히도록 하단 안내에 어두운 배경을 둔다 */}
      {/* 셀카 화면은 카메라 가까이 위쪽에 모으되, 떠 있는 상단 바(top-5 + h-12) 아래에서 시작한다 */}
      <div
        className={`relative flex flex-col gap-3.5 px-7 pb-[18px] ${selfie ? "pt-[84px]" : "pt-2"}`}
      >
        {selfie && (
          <SelfiePreview className="mx-auto aspect-[3/4] w-[70%]">
            {countdown !== null && (
              <span
                role="status"
                aria-live="assertive"
                aria-label={`마지막 사진 촬영까지 ${countdown}초`}
                className="font-serif text-[clamp(96px,22vw,180px)] leading-none tabular-nums"
              >
                {countdown}
              </span>
            )}
          </SelfiePreview>
        )}
        {!selfie && (
          <div
            className={cn(
              "-mx-3 flex flex-col gap-3.5 rounded-[22px] bg-night/85 px-4 py-4 shadow-modal backdrop-blur-xl transition-[background,box-shadow] duration-500",
              flash && "bg-night/95 ring-2 ring-blush",
            )}
          >
            {flash && (
              <span role="status" className="text-[17px] font-bold text-blush">
                {enteredStepNotice(flash)}
              </span>
            )}
            <div className="flex items-end gap-3">
              <span className="shrink-0 font-serif text-[34px] leading-[.9] text-blush italic tabular">
                {String(g + 1).padStart(2, "0")}
              </span>
              <h1 className="font-display text-[26px] leading-[1.15] text-white">{info.title}</h1>
              {groupDetail && (
                <span className="shrink-0 text-[15px] text-line-2 tabular">{groupDetail}</span>
              )}
              {visibleGauge && meterText && (
                <span
                  className="ml-auto shrink-0 text-[20px] leading-tight font-extrabold whitespace-nowrap transition-colors"
                  style={{ color: meterColor }}
                >
                  {meterText}
                </span>
              )}
              {shownActs.length > 0 && (
                <button
                  type="button"
                  onClick={() => setActsOpen((o) => !o)}
                  aria-expanded={actsOpen}
                  aria-controls="tutorial-acts"
                  aria-label={actsOpen ? "설명 접기" : "설명 펴기"}
                  className={cn(
                    "flex size-10 shrink-0 items-center justify-center self-start rounded-full bg-white/10 text-white hover:bg-white/20",
                    !(visibleGauge && meterText) && "ml-auto",
                  )}
                >
                  <ChevronDown
                    className={cn("size-6 transition-transform", actsOpen && "rotate-180")}
                    strokeWidth={2.4}
                    aria-hidden
                  />
                </button>
              )}
            </div>
            {/* 단계의 동작을 모두 카드로 띄운다. 접으면 제목·게이지만 남긴다 */}
            {actsOpen && (
              <div id="tutorial-acts" className="flex flex-col gap-2">
                {shownActs.map((i) => (
                  <ActCard
                    key={info.acts[i].text}
                    n={i + 1}
                    act={info.acts[i]}
                    doneWhen={i === info.acts.length - 1 ? info.doneWhen : null}
                  />
                ))}
              </div>
            )}

            {visibleGauge && (
              <DensityMeter
                value={display?.bar ?? null}
                color={meterColor}
                blocked={meterBlocked}
              />
            )}
            {gaugeDebug && (
              <GaugeDebug
                baseline={baseline.status}
                reading={gaugeMeasure.reading}
                display={display}
                areas={gaugeMeasure.areas.map((a) => a.cells)}
                made={gaugeMeasure.made}
              />
            )}
          </div>
        )}

        {selfie && countdown === null && shot.state === "idle" && (
          <p
            role="status"
            className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-ink"
          >
            얼굴 전체가 화면에 들어오게 맞춘 뒤 촬영하기를 눌러 주세요.
          </p>
        )}
        {selfie && countdown !== null && (
          <p className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-ink">
            잠시 후 마지막 사진을 촬영해요. 아래 버튼을 누르면 취소할 수 있어요.
          </p>
        )}
        {shot.state === "outOfView" && (
          <p
            role="status"
            className="rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-ink"
          >
            {last ? "얼굴 전체가" : "이 단계 부위가"} 화면에 다 보이게 조금 뒤로 가 주세요. 촬영을
            그만두려면 왼쪽 버튼을 눌러 주세요.
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
        {shot.state === "failed" && countdown === null && !reloadRegions && (
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
              if (posing) return setPosing(false);
              if (step > 0) goStep(step - 1, false);
            }}
            label={shot.saving ? "저장 중…" : shot.shooting ? "촬영 취소" : "이전 단계"}
            disabled={shot.saving || (!shot.shooting && step === 0)}
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
          detail={prepDetail ?? undefined}
          info={info}
          refProduct={info.product}
          match={pr}
          pick={pick}
          baseline={
            baselineNeeded
              ? {
                  frames: baseline.status.frames,
                  total: 15,
                  ready: stepBaseline !== null,
                  canSkip: canSkipBaseline,
                }
              : undefined
          }
          onStart={() => {
            if (!baselineNeeded || stepBaseline || canSkipBaseline) {
              if (baselineNeeded && !stepBaseline) setSkippedBaselineKey(baselineKey);
              setReady(true);
            }
          }}
        />
      )}

      {cameraTuning && !canSkipBaseline && (
        <div
          className="pointer-events-none absolute inset-0 z-[6] flex flex-col items-center justify-center gap-3 bg-night px-8 text-center text-white"
          role="status"
          aria-live="polite"
        >
          <span className="font-display text-[40px] leading-tight">
            카메라 밝기를 맞추고 있어요
          </span>
          <span className="text-[19px] font-semibold text-white/80">
            잠시 정면을 보고 가만히 있어 주세요
          </span>
        </div>
      )}

      {!ready &&
        !cameraTuning &&
        !canSkipBaseline &&
        baselineNeeded &&
        !stepBaseline &&
        (baseline.status.front === false || baselineStalled) && (
          <div
            className="pointer-events-none absolute inset-0 z-[6] flex flex-col items-center justify-center gap-3 bg-night/85 px-8 text-center text-white backdrop-blur-sm"
            role="alert"
            aria-live="assertive"
          >
            <span className="font-display text-[44px] leading-tight">카메라 렌즈를 봐 주세요</span>
            <span className="text-[19px] font-semibold text-white/80">
              화면이 아니라 카메라를 바라보면 사진 수집을 계속해요
            </span>
          </div>
        )}

      {/* 준비 카드처럼 상단 바(z-[5]) 아래에 깔아, 저장이 계속 실패해도 나가기를 누를 수 있게 한다 */}
      {review && (
        <div className="absolute inset-0 z-[4] flex flex-col items-center gap-3.5 bg-night px-7 pt-[84px] pb-[18px]">
          <div className="relative aspect-[3/4] w-[70%] overflow-hidden rounded-[24px] bg-black">
            {/* eslint-disable-next-line @next/next/no-img-element -- 메모리의 data URL이라 next/image가 필요 없다 */}
            <img
              src={review.url}
              alt="방금 찍은 마지막 사진"
              className="absolute inset-0 size-full object-contain"
            />
          </div>
          <p className="text-[19px] font-bold text-white">이 사진으로 완성할까요?</p>
          {reviewError !== null && (
            <p
              role="alert"
              className="w-full rounded-[18px] bg-white/90 px-5 py-3 text-[17px] font-bold text-error"
            >
              사진을 저장하지 못했어요. {errorMessage(reviewError)} 다시 시도하거나 다시 찍어
              주세요.
            </p>
          )}
          <div className="flex w-full items-center gap-3">
            <PillButton
              variant="line"
              size="cta"
              onClick={retake}
              disabled={reviewSaving}
              className="text-white"
            >
              다시 찍기
            </PillButton>
            <PillButton
              size="cta"
              trailing
              onClick={confirmReview}
              disabled={reviewSaving}
              className="min-w-0 flex-1"
            >
              {reviewSaving ? "저장 중…" : "이 사진으로 완성"}
            </PillButton>
          </div>
        </div>
      )}

      <StepList
        open={listOpen}
        items={groups.map((x) => ({
          title: steps
            .slice(x.start, x.end)
            .map((s) => s.title)
            .join(" · "),
          product: steps[x.start].product?.full ?? null,
          // 사진은 묶음 마지막 단계에 남는다
          done: !!stepPhoto(run.id, steps[x.end - 1].stepId),
        }))}
        current={g}
        onGo={goGroup}
        onFinish={finishHere}
        onClose={() => setListOpen(false)}
      />
      <ExitModal open={exitAsk} onQuit={quit} onClose={() => setExitAsk(false)} />
    </main>
  );
}
