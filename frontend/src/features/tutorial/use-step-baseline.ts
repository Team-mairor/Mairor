"use client";

import { useCallback, useEffect, useState } from "react";

import { useGaugeBaseline } from "@/features/gauge";
import type { RegionName } from "@/vision/face";

/** 모은 사진이 이만큼 늘지 않으면 멈춘 것으로 본다 */
const STALL_MS = 1000;
/** 다시 모은 뒤 그 사람 정면 30장(200ms 간격)을 배울 시간. 이 동안은 사진 수가 늘지 않는다 */
const RETRY_GRACE_MS = 8000;

/**
 * 단계 준비 카드가 떠 있는 동안 바르기 전 얼굴(게이지 기준)을 모으고, 못 모으면 막힌 이유를 알린다.
 * 첫 단계는 눈 화장 전 맨얼굴·흰자를, 게이지 단계는 바르기 전 해당 부위를 다시 모은다.
 * 기준을 모아야만 단계를 시작할 수 있다
 */
export function useStepBaseline({
  runId,
  step,
  makeup,
  regions,
  ready,
  showGauge,
  exitAsk,
  paused,
  recordingNext,
}: {
  runId: string;
  step: number;
  makeup: string;
  /** 기준 사진에 온전히 보여야 하는 지금 단계 부위 */
  regions: readonly RegionName[] | undefined;
  /** 준비 카드를 닫고 단계를 시작했다 */
  ready: boolean;
  showGauge: boolean;
  exitAsk: boolean;
  paused: boolean;
  /** 묶음 안 다음 단계가 게이지를 띄워 그 시작 기준에 쓸 사진을 남겨야 한다 */
  recordingNext: boolean;
}) {
  const key = `${runId}:${step}`;
  const gaugeActive = ready && showGauge && !exitAsk && !paused;
  const needed = step === 0 || showGauge;
  // 게이지가 이번 단계 화장만 재도록 단계 준비 카드가 떠 있는 동안 바르기 전 얼굴을 모은다.
  // 묶음 안 다음 단계는 카드 없이 시작하므로 이번 단계 동안 사진을 남겨 두었다가 그 단계 기준으로 쓴다
  const baseline = useGaugeBaseline({
    runId,
    step,
    collecting: !ready && needed,
    makeup,
    regions,
    recording: ready && recordingNext && !paused,
    measuring: gaugeActive,
  });
  const stepBaseline = baseline.stepBaseline(step);
  const cameraTuning = !ready && needed && !stepBaseline && baseline.status.lock === null;
  const [stalledAt, setStalledAt] = useState<{ key: string; frames: number } | null>(null);
  const [retried, setRetried] = useState<{ key: string; count: number } | null>(null);
  const { frames, lock } = baseline.status;
  useEffect(() => {
    if (ready || !needed || stepBaseline || lock === null) return;
    // 다시 모으면 사진이 한 장도 안 늘어도 그 사람 정면을 먼저 배우는 중이라, 그동안은 멈춘 것으로 보지 않는다
    const wait = retried?.key === key && frames === 0 ? RETRY_GRACE_MS : STALL_MS;
    const timer = setTimeout(() => setStalledAt({ key, frames }), wait);
    return () => clearTimeout(timer);
  }, [ready, needed, stepBaseline, frames, lock, key, retried]);
  const { restart } = baseline;
  /** 멈춘 기준 사진 모으기를 처음부터 다시 한다. 그 뒤로도 모이지 않으면 멈춘 안내가 다시 뜬다 */
  const retry = useCallback(() => {
    restart();
    setStalledAt(null);
    setRetried((prev) => ({ key, count: (prev?.key === key ? prev.count : 0) + 1 }));
  }, [restart, key]);
  const stalled =
    !cameraTuning &&
    !ready &&
    needed &&
    !stepBaseline &&
    stalledAt?.key === key &&
    stalledAt.frames === frames;

  return {
    baseline,
    stepBaseline,
    needed,
    gaugeActive,
    cameraTuning,
    stalled,
    retry,
  };
}
