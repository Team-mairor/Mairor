"use client";

import { useEffect, useRef, useState } from "react";

import { readCover } from "@/domain/gauge/cover";
import { FRAME } from "@/domain/gauge/stability";
import { loadCellSampler, type Samplers } from "@/features/gauge";
import { StartCamera, useCamera, useFaceFrame, type FaceFrame } from "@/vision/face";
import { OcclusionRunner, type OcclusionStatus } from "@/vision/occlusion";

import { maxZone, zoneCovers } from "./zones";

/**
 * 가림 찾기 실기기 확인 화면(개발 화면). 카메라를 켜고, scripts/occlusion-live.mjs가 시키는 대로
 * 단계(phase)를 바꿔 가며 단계마다 가린 몫 · 얼굴 추적 속도(FPS) · 가림 찾기 상태를 모아 window.__OCC_LIVE__에 둔다.
 * 사람은 화면에 나오는 큰 글자대로 손동작만 하면 된다
 */
interface PhaseStats {
  phase: string;
  seconds: number;
  occlusionOn: boolean;
  /** 얼굴 추적 결과 수(얼굴이 없는 결과 포함)와 그 가운데 얼굴이 보인 수 */
  frames: number;
  faceFrames: number;
  /** 얼굴 추적 결과가 1초에 몇 번 왔는지 */
  fps: number | null;
  /** 단계가 바뀐 뒤 SETTLE_MS가 지난 결과 가운데 가림 표로 가린 몫을 낸 수 */
  zoneSamples: number;
  /** 가장 많이 가린 구역의 몫: 평균과 최대 */
  maxZoneMean: number | null;
  maxZoneMax: number | null;
  /** 그 몫이 문턱(frame.areaCoverMax)을 넘은 결과 수(안정 구간)와, 단계가 시작된 뒤 처음 넘기까지(ms, 사람이 손을 옮기는 시간 포함) */
  overFrames: number;
  firstOverMs: number | null;
  /** 단계가 끝날 때(지금) 가림 찾기 상태 */
  status: OcclusionStatus | null;
}

interface LiveCommand {
  phase: string;
  text: string;
  seconds: number;
  occlusion: boolean;
}

interface Live {
  stats: PhaseStats;
  startedAt: number;
  sumMaxZone: number;
}

declare global {
  interface Window {
    __OCC_LIVE__?: {
      version: 1;
      cameraStatus: string;
      ready: boolean;
      frames: number;
      faceFrames: number;
      occlusion: OcclusionStatus | null;
      phases: PhaseStats[];
      current: PhaseStats | null;
    };
    __OCC_LIVE_CMD__?: (command: LiveCommand) => boolean;
  }
}

const emptyStats = (command: LiveCommand): PhaseStats => ({
  phase: command.phase,
  seconds: command.seconds,
  occlusionOn: command.occlusion,
  frames: 0,
  faceFrames: 0,
  fps: null,
  zoneSamples: 0,
  maxZoneMean: null,
  maxZoneMax: null,
  overFrames: 0,
  firstOverMs: null,
  status: null,
});

/**
 * 단계가 바뀐 직후에는 사람이 손을 옮기는 중이고, 직전 단계 가림 결과가 최대 몇 초 더 남는다.
 * 그동안은 가린 몫 · 오탐 집계에서 뺀다(FPS와 처음 넘은 시각은 처음부터 센다)
 */
const SETTLE_MS = 4000;

const round = (value: number, digits = 3) => {
  const m = 10 ** digits;
  return Math.round(value * m) / m;
};

export default function OcclusionLivePage() {
  const { status: cameraStatus, error, videoRef } = useCamera();
  const runner = useRef<OcclusionRunner | null>(null);
  const samplers = useRef<Samplers | null>(null);
  const occlusionOn = useRef(true);
  const current = useRef<Live | null>(null);
  const finished = useRef<PhaseStats[]>([]);
  const totals = useRef({ frames: 0, faceFrames: 0 });
  const cameraRef = useRef(cameraStatus);
  const [shown, setShown] = useState({ text: "카메라를 켜는 중", remaining: 0, detail: "" });

  useEffect(() => {
    cameraRef.current = cameraStatus;
  }, [cameraStatus]);

  // 가림 찾기 실행기와 칸 표본, 스크립트가 읽고 시킬 창 값
  useEffect(() => {
    const r = new OcclusionRunner();
    runner.current = r;
    r.start();
    let live = true;
    loadCellSampler()
      .then((s) => {
        if (live) samplers.current = s;
      })
      .catch(() => {});

    const snapshot = (live: Live | null): PhaseStats | null => {
      if (!live) return null;
      const s = { ...live.stats };
      const seconds = (performance.now() - live.startedAt) / 1000;
      s.fps = seconds > 0 ? round(s.frames / seconds, 1) : null;
      s.maxZoneMean = s.zoneSamples ? round(live.sumMaxZone / s.zoneSamples) : null;
      s.status = r.status;
      return s;
    };
    Object.defineProperty(window, "__OCC_LIVE__", {
      configurable: true,
      get: () => ({
        version: 1 as const,
        cameraStatus: cameraRef.current,
        ready: totals.current.faceFrames > 10 && r.status.state !== "loading",
        frames: totals.current.frames,
        faceFrames: totals.current.faceFrames,
        occlusion: r.status,
        phases: finished.current,
        current: snapshot(current.current),
      }),
    });
    window.__OCC_LIVE_CMD__ = (command) => {
      const done = snapshot(current.current);
      if (done) finished.current = [...finished.current, done];
      current.current = { stats: emptyStats(command), startedAt: performance.now(), sumMaxZone: 0 };
      occlusionOn.current = command.occlusion;
      setShown({ text: command.text, remaining: command.seconds, detail: command.phase });
      // 화면을 보지 않아도 단계가 바뀐 걸 알 수 있게 진동을 낸다
      navigator.vibrate?.(250);
      return true;
    };
    const timer = setInterval(() => {
      const live = current.current;
      if (!live) return;
      const left = Math.max(0, live.stats.seconds - (performance.now() - live.startedAt) / 1000);
      setShown((prev) =>
        prev.remaining === Math.ceil(left) ? prev : { ...prev, remaining: Math.ceil(left) },
      );
    }, 250);
    return () => {
      live = false;
      clearInterval(timer);
      r.dispose();
      runner.current = null;
      delete window.__OCC_LIVE__;
      delete window.__OCC_LIVE_CMD__;
    };
  }, []);

  useFaceFrame((frame: FaceFrame | null) => {
    const live = current.current;
    totals.current.frames++;
    if (live) live.stats.frames++;
    const fresh = frame && frame.trackingState !== "lost" && frame.trackingState !== "hold";
    if (!fresh) return;
    totals.current.faceFrames++;
    if (live) live.stats.faceFrames++;
    const video = videoRef.current;
    const sampler = samplers.current;
    const r = runner.current;
    if (!live || !occlusionOn.current || !r || !video || !sampler) return;
    const now = performance.now();
    r.feed(video, frame.landmarks, now);
    const mask = r.latestFor(now);
    if (!mask) return;
    const cover = readCover(
      mask,
      { width: video.videoWidth, height: video.videoHeight },
      frame.landmarks,
      sampler.cells,
    );
    const worst = maxZone(zoneCovers(cover));
    const s = live.stats;
    const elapsed = now - live.startedAt;
    if (worst > FRAME.areaCoverMax) s.firstOverMs ??= Math.round(elapsed);
    if (elapsed < SETTLE_MS) return;
    s.zoneSamples++;
    live.sumMaxZone += worst;
    s.maxZoneMax = round(Math.max(s.maxZoneMax ?? 0, worst));
    if (worst > FRAME.areaCoverMax) s.overFrames++;
  });

  return (
    <>
      <StartCamera />
      <div className="pointer-events-none absolute inset-0 z-10 flex flex-col items-center justify-center gap-6 bg-black/55 p-8 text-center text-white">
        <p className="text-5xl leading-snug font-bold">
          {cameraStatus === "error"
            ? `카메라를 열지 못했어요: ${error?.message ?? ""}`
            : shown.text}
        </p>
        {shown.remaining > 0 && (
          <p className="text-8xl font-bold tabular-nums">{shown.remaining}</p>
        )}
        <p className="text-sm text-white/60">{shown.detail}</p>
      </div>
    </>
  );
}
