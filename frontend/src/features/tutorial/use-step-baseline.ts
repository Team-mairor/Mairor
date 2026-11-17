"use client";

import { useEffect, useState } from "react";

import { useGaugeBaseline } from "@/features/gauge";
import type { RegionName } from "@/vision/face";

/**
 * 단계 준비 카드가 떠 있는 동안 바르기 전 얼굴(게이지 기준)을 모으고, 못 모으면 막힌 이유를 알린다.
 * 첫 단계는 눈 화장 전 맨얼굴·흰자를, 게이지 단계는 바르기 전 해당 부위를 다시 모은다.
 * 모으지 못해도 일정 시간이 지나면 게이지 없이 시작할 수 있다
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
  const [skippedKey, setSkippedKey] = useState<string | null>(null);
  const skipped = skippedKey === key;
  const gaugeActive = ready && showGauge && !skipped && !exitAsk && !paused;
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
  const [escapeKey, setEscapeKey] = useState<string | null>(null);
  const { frames, lock } = baseline.status;
  useEffect(() => {
    if (ready || !needed || stepBaseline || lock === null) return;
    const timer = setTimeout(() => setStalledAt({ key, frames }), 1000);
    return () => clearTimeout(timer);
  }, [ready, needed, stepBaseline, frames, lock, key]);
  useEffect(() => {
    if (ready || !needed || stepBaseline) return;
    const timer = setTimeout(() => setEscapeKey(key), 8000);
    return () => clearTimeout(timer);
  }, [ready, needed, stepBaseline, key]);
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
    skipped,
    gaugeActive,
    cameraTuning,
    stalled,
    /** 기준을 못 모은 채 오래 기다렸다. 게이지 없이 시작할 수 있다 */
    canSkip: escapeKey === key,
    skip: () => setSkippedKey(key),
  };
}
