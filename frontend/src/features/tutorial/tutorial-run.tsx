"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { pickOf } from "@/domain/check";
import { needsMore } from "@/domain/gauge";
import { groupIndexOf, groupSteps, productStepKey } from "@/domain/guide";
import {
  abandonExecution,
  deleteFaceRegistration,
  uploadStepPhoto,
  useGuide,
  useRunQuery as useQuery,
} from "@/domain/guide-run";
import {
  matchFor,
  runHref,
  saveStepPhoto,
  stepPhoto,
  useMyPouch,
  useRun,
  type StepPhoto,
} from "@/domain/session";
import { GaugeDebug, useGaugeMeasure } from "@/features/gauge";
import { TutorialViewport, useTutorialCrop } from "@/features/guide";
import { LiveNote, parseAlert, useLiveState } from "@/features/live";
import { ApiError } from "@/lib/api";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { isMirror, subscribeMirror } from "@/lib/mirror";
import { type RegionName } from "@/vision/face";
import {
  loadDefaultGuideSet,
  resolveStep,
  useBrowFit,
  useGuideTrackingIssue,
  type GuideArea,
  type GuideSet,
} from "@/vision/guide";

import { ExitModal } from "./exit-modal";
import { LackMoreModal, TooDarkModal } from "./gauge-notice-modals";
import { ProductChip } from "./product-chip";
import { SelfiePreview } from "./selfie-preview";
import { StepActions } from "./step-actions";
import { PrepCard } from "./step-cards";
import { StepList } from "./step-list";
import { StepPanel } from "./step-panel";
import { TutorialTopBar } from "./top-bar";
import {
  CameraTuningOverlay,
  CountdownOverlay,
  LookAtCameraOverlay,
  PhotoReview,
  ShotNotices,
} from "./tutorial-overlays";
import {
  ENTER_FLASH_MS,
  photoRegionsOf,
  type EnteredStep,
  type TutorialStep,
} from "./tutorial-steps";
import { useFinalCountdown } from "./use-final-countdown";
import { useFinalReview } from "./use-final-review";
import { useGaugeDebug } from "./use-gauge-debug";
import { useSmoothedGauge } from "./use-smoothed-gauge";
import { useStepBaseline } from "./use-step-baseline";
import { LABEL_COLOR, LABEL_TEXT, useStepGaugeRule } from "./use-step-gauge-rule";
import { useStepShot } from "./use-step-shot";
import { useTooDarkNotice } from "./use-too-dark-notice";

/**
 * 상단 바는 연속한 같은 제품 단계를 한 칸으로 묶고, 묶음의 마지막 단계를 넘길 때 확인 창 없이 사진을 한 장 남긴다.
 * 단계 목록에서 아무 묶음으로나 가고, 원하는 단계까지만 하고 지금 단계에서 완성할 수 있다.
 * 사진 저장 동의는 필수이고 튜토리얼 안내에서 받는다.
 * 진하기 게이지는 카메라에서 잰 이번 단계 화장 효과를 레퍼런스와 견준 값이다(features/gauge).
 */
export function TutorialRun({ steps, area }: { steps: TutorialStep[]; area: GuideArea | null }) {
  const router = useRouter();
  const query = useQuery();
  const { pouch } = useMyPouch();
  const { run, updateRun, endRun, completeRun, isCurrentRun } = useRun();
  const { load } = useGuide();
  const alert = parseAlert(query?.get("alert"));

  const [defaults, setDefaults] = useState<GuideSet | null>(null);
  const [step, setStep] = useState(0);
  // false면 단계 준비 카드(제품·할 일·끝내는 기준)를 띄운다. 앞으로 갈 때만 띄우고, 이전 단계로 돌아갈 때는 띄우지 않는다
  const [ready, setReady] = useState(false);
  const [exitAsk, setExitAsk] = useState(false);
  const [listOpen, setListOpen] = useState(false);
  // 목록에서 지금 단계에서 완성하기를 골랐는지. 마지막 단계처럼 얼굴 전체 사진을 찍고 끝낸다
  const [finishing, setFinishing] = useState(false);
  // 미러필름에서 마지막 사진 전에 카메라 화면을 띄우고 자세를 맞추는 중인지
  const [posing, setPosing] = useState(false);
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
  const pr = info.ref ? matchFor(info.ref, run, pouch) : null;
  // 실제 가이드의 선택은 표시만 하고 촬영·게이지 판단에는 쓰지 않는다
  const pick = info.ref ? null : pickOf(info.stepId, run.choice, pouch);
  const hasProduct = !!pr && pr.kind !== "none";
  // 바르는 단계인지. 샘플에서 제품이 없는 단계만 바로 건너뛸 수 있다
  const paced = hasProduct || !pr;
  const last = step >= steps.length - 1 || finishing;

  // 레퍼런스 게이지 기준이 있는 단계만 게이지를 띄우고, 고른 제품에 따라 숨기거나 색감을 뺀다
  const gaugeRule = useStepGaugeRule({
    steps,
    step,
    info,
    area,
    executionId: run.executionId,
    pick,
    choice: run.choice,
    pouch,
    groupLast,
  });
  const { subs, reference, rule, showGauge, nextNeedsBaseline } = gaugeRule;
  // 한 단계 안에서 영역이 바뀌어도 나눠 넘기지 않고 모든 영역을 한 번에 그린다
  const resolved = useMemo(
    () => resolveStep(info.stepId, subs, defaults, info.makeup),
    [info.stepId, info.makeup, subs, defaults],
  );
  // 눈썹은 등록 사진의 원래 눈썹 모양·앞머리·꼬리에 맞춘다
  const guideStep = useBrowFit(resolved, run.id);
  const paused = run.mode === "guide" && (load.status !== "ready" || load.checking || !!load.error);
  const gate = useStepBaseline({
    runId: run.id,
    step,
    makeup: info.makeup,
    regions: guideStep?.regions,
    ready,
    showGauge,
    exitAsk,
    paused,
    recordingNext: nextNeedsBaseline,
  });
  const { baseline, stepBaseline, gaugeActive } = gate;
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
  const review = useFinalReview({ save: savePhoto });
  // 마지막 사진은 리포트 대표 사진이라 얼굴 전체가 보일 때 찍고, 저장 전에 다시 찍을 수 있게 한다
  const shot = useStepShot(
    photoRegions,
    async (photo) => {
      if (!last) return savePhoto(photo);
      review.begin(photo);
    },
    last,
  );
  const { cancel: cancelShot } = shot;
  const finalCountdown = useFinalCountdown({
    onFire: () => shot.start(),
    interrupt: [blocked, paused, exitAsk],
  });
  const { countdown } = finalCountdown;
  const selfie = mirror && last && (posing || countdown !== null || shot.shooting || shot.saving);

  // 개발 도구에서 ?gauge를 붙이면 잰 값과 못 잰 이유를 띄운다
  const gaugeDebug = useGaugeDebug(!!query?.has("gauge"));
  const gaugeMeasure = useGaugeMeasure({
    // 먼 얼굴은 색이 부정확하므로 마지막 값을 유지하고, 가까워도 해당 부위가 보이면 계속 잰다
    active: gaugeActive && reason !== "far",
    // 기준이 대체 제품 쪽으로 바뀌면 다듬던 값을 이어 쓰지 않는다
    key: reference ? `${run.id}:${reference.subStepId}:${rule?.basis}` : null,
    makeup: info.makeup,
    gauge: gaugeRule.measureGauge,
    guideSets: gaugeRule.measured,
    madeSets: gaugeRule.madeSets,
    start: stepBaseline,
    white: baseline.status.white,
    debug: gaugeDebug,
    onShot: baseline.record,
  });
  const { display } = gaugeMeasure;
  // 화면에 보이는 막대 · 문구 · 연함 / 진함 창은 모두 이 다듬은 값에서 정한다. 원래 값은 디버그에만 보인다
  const smoothed = useSmoothedGauge(display?.bar ?? null);
  const shown = useMemo(
    () => (display ? { ...display, bar: smoothed.bar, label: smoothed.label } : null),
    [display, smoothed],
  );
  const gaugeUnavailable =
    display?.reason === "thinArea" ||
    display?.reason === "weakReference" ||
    display?.reason === "noReference" ||
    display?.reason === "noWhite";
  const visibleGauge = showGauge && !gaugeUnavailable;
  // 이전 화면에서 기준 없이 시작한 실행도 준비 카드를 다시 열어 같은 단계 기준을 모은다
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 기준이 없는 기존 실행을 준비 카드로 복구한다
    if (ready && showGauge && display?.reason === "noBaseline") setReady(false);
  }, [ready, showGauge, display?.reason]);
  // 너무 진하면 멈추고 확인시키고, 단계를 넘길 때 연하면 더 바를지 묻는다. 둘 다 단계마다 새로 시작한다
  const stepKey = `${run.id}:${step}`;
  const gaugeReading = gaugeActive && visibleGauge && reason !== "far";
  const tooDark = useTooDarkNotice({ display: shown, enabled: gaugeReading, stepKey });
  const [lackKey, setLackKey] = useState<string | null>(null);
  const lackAsked = useRef(new Set<string>());
  const gaugeLabel = shown?.label ?? null;
  const meterBlocked = paused || reason === "far" || shown?.bar == null;
  const meterColor = !gaugeLabel ? "#20DFFF" : LABEL_COLOR[gaugeLabel];
  const meterText = meterBlocked
    ? reason === "far"
      ? "조금 가까이 와 주세요"
      : shown?.bar == null
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

  // 가이드를 다시 확인하는 동안 촬영 대기를 접는다
  useEffect(() => {
    if (paused) cancelShot();
  }, [paused, cancelShot]);

  // 진행바·이전 버튼으로 옮기면 촬영 대기를 접는다. 예전 단계 사진으로 넘어가지 않게
  function goStep(i: number, prep = true) {
    finalCountdown.cancel();
    cancelShot();
    setPosing(false);
    review.reset();
    setStep(i);
    setReady(!prep);
    setEntered(null);
    setFinishing(false);
    setListOpen(false);
  }
  /** 촬영을 기다리는 중에 창을 열면 뒤에서 단계가 넘어가지 않게 대기를 접는다 */
  const stopWaiting = () => {
    finalCountdown.cancel();
    cancelShot();
    setPosing(false);
  };
  const openList = () => {
    stopWaiting();
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
    const picked = pickOf(s.stepId, run.choice, pouch);
    if (picked.kind === "skipped") return null;
    const matched = s.ref ? matchFor(s.ref, run, pouch).p : null;
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
    if (finalCountdown.cancel()) return;
    if (shot.shooting || shot.saving || paused) return;
    // 레퍼런스보다 연하면 넘기기 전에 한 번 묻는다. 사용자가 목록에서 여기서 끝내겠다고 한 때는 묻지 않는다
    if (!finishing && gaugeReading && needsMore(shown) && !lackAsked.current.has(stepKey)) {
      lackAsked.current.add(stepKey);
      setLackKey(stepKey);
      return;
    }
    if (!groupLast && !finishing) return enterNextInGroup();
    if (reloadRegions) {
      setDefaultsFailed(false);
      return loadDefaults();
    }
    if (!last) return shot.start();
    // 미러필름은 카메라 화면을 먼저 띄우고, 자세를 맞춘 뒤 한 번 더 눌러야 카운트다운을 시작한다
    if (mirror && !posing) return setPosing(true);
    finalCountdown.start();
  };
  const back = () => {
    if (finalCountdown.cancel()) return;
    if (shot.saving) return;
    // 촬영을 기다리는 중이면(부위가 계속 화면 밖 등) 대기만 접고 지금 단계에 머문다
    if (shot.shooting) return cancelShot();
    if (posing) return setPosing(false);
    if (step > 0) goStep(step - 1, false);
  };
  const quit = () => {
    leaving.current = true;
    finalCountdown.cancel();
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
  const backLabel = shot.saving ? "저장 중…" : shot.shooting ? "촬영 취소" : "이전 단계";

  return (
    <main className="relative flex flex-1 flex-col">
      <TutorialViewport step={canRender && !selfie ? guideStep : null} />
      {!selfie && <div className="flex-1" />}

      {countdown !== null && !selfie && <CountdownOverlay countdown={countdown} />}

      <TutorialTopBar
        groups={groups}
        group={g}
        onExit={() => {
          stopWaiting();
          setExitAsk(true);
        }}
        listDisabled={shot.saving || review.saving}
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
        {selfie ? (
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
        ) : (
          <StepPanel
            info={info}
            groupNumber={g + 1}
            groupDetail={groupDetail}
            flash={flash}
            meter={{
              show: visibleGauge,
              text: meterText,
              value: shown?.bar ?? null,
              color: meterColor,
              blocked: meterBlocked,
            }}
            debug={
              gaugeDebug && (
                <GaugeDebug
                  baseline={baseline.status}
                  reading={gaugeMeasure.reading}
                  display={display}
                  areas={gaugeMeasure.areas.map((a) => a.cells)}
                  made={gaugeMeasure.made}
                />
              )
            }
          />
        )}

        <ShotNotices
          selfie={selfie}
          countdown={countdown}
          shot={shot}
          last={last}
          reloadRegions={reloadRegions}
        />

        <StepActions
          back={{
            label: backLabel,
            disabled: shot.saving || (!shot.shooting && step === 0),
            onClick: back,
          }}
          next={{
            label: shot.saving ? "저장 중…" : nextLabel,
            disabled: shot.saving,
            onClick: next,
          }}
        />
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
            gate.needed
              ? {
                  frames: baseline.status.frames,
                  total: 15,
                  ready: stepBaseline !== null,
                }
              : undefined
          }
          onStart={() => {
            if (!gate.needed || stepBaseline) setReady(true);
          }}
        />
      )}

      {gate.cameraTuning && <CameraTuningOverlay />}
      {!ready &&
        !gate.cameraTuning &&
        gate.needed &&
        !stepBaseline &&
        (baseline.status.front === false || gate.stalled) && (
          <LookAtCameraOverlay onRetry={gate.stalled ? gate.retry : undefined} />
        )}

      {review.photo && (
        <PhotoReview
          photo={review.photo}
          error={review.error}
          saving={review.saving}
          onRetake={review.retake}
          onConfirm={review.confirm}
        />
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
      <LackMoreModal
        open={lackKey === stepKey}
        onMore={() => setLackKey(null)}
        onSkip={() => {
          setLackKey(null);
          next();
        }}
      />
      <TooDarkModal open={tooDark.open} onConfirm={tooDark.confirm} />
    </main>
  );
}
