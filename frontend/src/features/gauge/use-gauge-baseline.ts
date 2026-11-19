"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  BaselineCollector,
  facing,
  FRAME_GAP_MS,
  FrontCenter,
  goodFrame,
  qualityOf,
  type Baseline,
  type FrameQuality,
} from "@/domain/gauge/baseline";
import { cellSampler, readCells, type CellLab, type Pixels } from "@/domain/gauge/cells";
import { eyeAspect, frameState } from "@/domain/gauge/frame";
import { nextStartBaseline, trimTail, type TailShot } from "@/domain/gauge/next-start";
import {
  registeredGaugeBaseline,
  type RegisteredGaugeBaseline,
} from "@/domain/gauge/registered-baseline";
import type { Samplers } from "@/domain/gauge/samplers";
import { FRAME, type FrameState } from "@/domain/gauge/stability";
import { eyeSampler, readEyePixels, whiteOfFrames } from "@/domain/gauge/white";
import {
  FRAME_STALE_MS,
  isRegionInView,
  lockControls,
  matchExposure,
  unlockControls,
  useCamera,
  useFaceFrame,
  type FaceFrame,
  type RegionName,
} from "@/vision/face";
import { loadFaceMesh } from "@/vision/overlay";

export type { Samplers };

let samplerPromise: Promise<Samplers> | null = null;
/** 칸 · 눈 구멍 표본 자리는 얼굴 지도로 정해져 한 번만 만든다 */
export function loadCellSampler(): Promise<Samplers> {
  samplerPromise ??= loadFaceMesh()
    .then((mesh) => ({ cells: cellSampler(mesh), eyes: eyeSampler(mesh) }))
    .catch((e) => {
      samplerPromise = null;
      throw e;
    });
  return samplerPromise;
}

/** 같은 캔버스를 다시 써서 지금 영상을 원본 그대로 읽는다 */
export function videoReader() {
  let canvas: HTMLCanvasElement | null = null;
  return (video: HTMLVideoElement): Pixels | null => {
    canvas ??= document.createElement("canvas");
    const { videoWidth: width, videoHeight: height } = video;
    if (!width || !height) return null;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0);
    return ctx.getImageData(0, 0, width, height);
  };
}

const videoTrack = (video: HTMLVideoElement | null) =>
  (video?.srcObject as MediaStream | null)?.getVideoTracks()[0] ?? null;

export interface GaugeBaselineStatus {
  /** 최근 얼굴이 정면이고 지금 단계 부위가 온전히 보여 기준 사진에 쓸 수 있는지 */
  front: boolean | null;
  /** 그 사람 정면 pitch. 아직 못 정했으면 null */
  center: number | null;
  /** 맨얼굴 기준. 첫 단계 준비 카드에서 다 모으지 못했으면 null */
  bare: Baseline | null;
  /** 지금 모으는 기준의 사진 수 */
  frames: number;
  /** 노출·화이트밸런스 잠금 결과. 잠그기 전에는 null */
  lock: Record<string, string> | null;
  /** 잠그는 데 걸린 시간(ms) */
  lockMs: number | null;
  /** 칸 색을 한 번 읽는 데 걸린 시간(ms) */
  readMs: number | null;
  /** 눈 화장 전 첫 기준 사진으로 잰 흰자 색(sRGB 0~255). 못 쟀으면 null */
  white: [number, number, number] | null;
  /** 최근 사진의 고개 각도와 눈 뜸(aspect는 점 6개 비율). 기준 사진이 안 모일 때 이유를 보려고 띄운다 */
  quality: (FrameQuality & { aspect: number }) | null;
}

export interface GaugeBaselineOptions {
  runId: string;
  step: number;
  collecting: boolean;
  /** 지금 단계 화장 종류. 눈 화장 단계에 들어서면 그 뒤로는 흰자를 재지 않는다 */
  makeup?: string;
  /** 기준 사진에 온전히 보여야 하는 지금 단계 부위 */
  regions?: readonly RegionName[];
  /** 묶음 안 다음 단계 시작 기준에 쓸 사진을 남기는 중인지 */
  recording?: boolean;
  /** 게이지가 재는 중이면 그 사진을 record로 받아 따로 읽지 않는다 */
  measuring?: boolean;
}

/** 한 실행 동안 모은 기준 */
const freshStore = (runId: string, registered: RegisteredGaugeBaseline | null = null) => ({
  runId,
  center: new FrontCenter(registered?.center),
  bare: registered?.baseline ?? (null as Baseline | null),
  white: registered?.white ?? (null as [number, number, number] | null),
  /** 지금 모으는 기준 사진의 눈 구멍 점 색. 흰자 색을 잴 때 쓴다 */
  eyes: [] as Float32Array[],
  /** 눈 화장 단계에 들어선 적이 있는지. 아이라인 · 속눈썹이 흰자 둘레를 덮으므로 그 뒤로는 흰자를 재지 않는다 */
  eyeMakeupSeen: false,
  /** 첫 모으기가 끝나기 전. 이때 만든 기준만 맨얼굴 기준이다 */
  first: registered === null,
  /** 카메라를 잠그는 중. 잠그는 동안은 화면 밝기가 바뀌어 기준 사진을 모으지 않는다 */
  locking: false,
  /** 카메라 잠금을 시도해 끝냈는지. 트랙이 준비되기 전에는 false라 기준을 모으지 않는다 */
  lockReady: registered !== null,
  steps: new Map<number, Baseline | null>(registered ? [[0, registered.baseline]] : []),
  collector: null as BaselineCollector | null,
  step: 0,
  /** 지금 단계 동안 남긴 최근 사진. 묶음 안 다음 단계 시작 기준을 여기서 고른다 */
  tail: [] as TailShot[],
  tailAt: -Infinity,
});
type Store = ReturnType<typeof freshStore>;

/** 모으던 기준을 그 단계 것으로 정한다. 첫 모으기면 맨얼굴 기준으로도 둔다 */
function finish(s: Store, collector: BaselineCollector) {
  const base = collector.build();
  s.steps.set(s.step, base);
  s.collector = null;
  // 맨얼굴 기준을 못 모았으면 눈 화장 전 다음 준비 카드에서 다 모은 사진으로 흰자를 잰다
  if (base && !s.white && s.eyes.length) s.white = whiteOfFrames(s.eyes);
  s.eyes = [];
  if (!s.first) return;
  s.first = false;
  s.bare = base;
}

/** 흰자를 아직 못 쟀고 눈 화장 전이면 기준 사진의 눈 구멍도 읽는다 */
const wantsWhite = (s: Store) => !s.white && !s.eyeMakeupSeen;

/** 노출은 자동 밝기에 맞추고, 화이트밸런스는 지원되는 기기에서 잠금을 시도한다. 잠그는 동안은 기준 사진을 모으지 않는다 */
async function lockCamera(video: HTMLVideoElement, track: MediaStreamTrack, signal: AbortSignal) {
  const started = performance.now();
  try {
    const exposure = await matchExposure(track, video, signal);
    if (signal.aborted) return null;
    const whiteBalance = await lockControls(track, ["whiteBalance"]);
    if (signal.aborted) return null;
    return { lock: { ...exposure, ...whiteBalance }, lockMs: performance.now() - started };
  } catch (e) {
    if (signal.aborted) return null;
    console.warn("카메라 노출·화이트밸런스를 잠그지 못했습니다", e);
    // 자동 상태로 모은 기준과 구분하도록 잠금 결과에 실패를 남긴다
    const reason = `실패: ${e instanceof Error ? e.message : String(e)}`;
    return { lock: { camera: reason }, lockMs: performance.now() - started };
  }
}

/**
 * 게이지 기준(맨얼굴 기준 · 단계 시작 기준)을 이번 실행 메모리에만 모은다. 저장하거나 보내지 않는다.
 * collecting인 동안(단계 준비 카드) 정면 · 눈 뜬 사진을 모아 그 단계 시작 기준을 만들고,
 * 첫 단계에서 모은 기준은 맨얼굴 기준으로도 쓴다. 첫 모으기를 시작할 때 노출 · 화이트밸런스를 먼저 잠그고
 * (잠근 뒤 색으로 기준을 잡아야 측정과 같은 카메라 설정이다) 나갈 때 푼다.
 * 준비 카드가 닫힐 때까지 다 모으지 못한 단계는 기준이 null이고, 첫 단계에서 못 모으면 맨얼굴 기준도 없다.
 * 흰자는 눈 화장 단계 전에 처음 다 모은 기준 사진으로 잰다
 */
export function useGaugeBaseline({
  runId,
  step,
  collecting,
  makeup,
  regions = [],
  recording = false,
  measuring = false,
}: GaugeBaselineOptions) {
  const { videoRef } = useCamera();
  const [status, setStatus] = useState<GaugeBaselineStatus>({
    front: null,
    center: null,
    bare: null,
    frames: 0,
    lock: null,
    lockMs: null,
    readMs: null,
    white: null,
    quality: null,
  });
  const shown = useRef(0);
  const store = useRef(freshStore(runId));
  const locked = useRef<MediaStreamTrack | null>(null);
  const lockAbort = useRef<AbortController | null>(null);
  const released = useRef<Promise<void>>(Promise.resolve());
  const sampler = useRef<Samplers | null>(null);
  const read = useRef(videoReader());

  const releaseCamera = useCallback(() => {
    lockAbort.current?.abort();
    lockAbort.current = null;
    const track = locked.current;
    locked.current = null;
    if (track)
      released.current = released.current.then(() => unlockControls(track).catch(() => {}));
  }, []);

  const startLock = useCallback((s: Store, video: HTMLVideoElement, track: MediaStreamTrack) => {
    if (s.lockReady || s.locking) return;
    s.locking = true;
    const controller = new AbortController();
    lockAbort.current = controller;
    locked.current = track;
    const waitForRelease = released.current;
    void waitForRelease
      .then(() => lockCamera(video, track, controller.signal))
      .then((result) => {
        if (controller.signal.aborted || store.current !== s) return;
        s.lockReady = true;
        if (result) setStatus((prev) => ({ ...prev, ...result }));
      })
      .finally(() => {
        s.locking = false;
        if (lockAbort.current === controller) lockAbort.current = null;
      });
  }, []);

  useEffect(() => {
    let live = true;
    loadCellSampler()
      .then((s) => live && (sampler.current = s))
      .catch((e) => console.warn("게이지 칸 표본을 만들지 못했습니다", e));
    return () => {
      live = false;
    };
  }, []);

  // 다른 실행의 기준은 쓰지 않는다
  useEffect(() => {
    if (store.current.runId === runId) return;
    store.current = freshStore(runId);
    // 새 실행은 그때 조명에 맞춰 다시 잠근다
    releaseCamera();
    setStatus((prev) => ({
      ...prev,
      front: null,
      center: null,
      bare: null,
      frames: 0,
      lock: null,
      lockMs: null,
      readMs: null,
      white: null,
      quality: null,
    }));
  }, [releaseCamera, runId, videoRef]);

  useEffect(() => {
    const s = store.current;
    if (s.runId !== runId || s.lockReady) return;
    const track = videoTrack(videoRef.current);
    const registered = registeredGaugeBaseline(runId, track);
    if (!registered || !track) return;
    store.current = freshStore(runId, registered);
    locked.current = track;
    setStatus((prev) => ({
      ...prev,
      center: registered.center,
      bare: registered.baseline,
      frames: registered.baseline.frames,
      lock: registered.lock,
      white: registered.white,
    }));
  }, [runId, videoRef]);

  useEffect(() => () => releaseCamera(), [releaseCamera]);

  // 눈 화장 단계에 들어서면 그 실행에서는 흰자를 더 재지 않는다. 준비 카드보다 먼저 정한다
  useEffect(() => {
    if (makeup && FRAME.eyeMakeups.includes(makeup)) store.current.eyeMakeupSeen = true;
  }, [makeup, runId]);

  // 준비 카드가 닫히거나 단계가 바뀌면 모으던 기준을 그 단계 것으로 정한다
  useEffect(() => {
    const s = store.current;
    if (collecting && s.steps.get(step) == null) {
      s.collector = new BaselineCollector();
      s.step = step;
      s.eyes = [];
      setStatus((prev) => ({ ...prev, front: null, frames: 0 }));
      const video = videoRef.current;
      const track = videoTrack(video);
      if (!s.lockReady && video && track) startLock(s, video, track);
      return () => {
        if (s.collector && s.step === step) finish(s, s.collector);
        setStatus((prev) => ({ ...prev, bare: s.bare, white: s.white }));
      };
    }
  }, [collecting, step, runId, startLock, videoRef]);

  const record = useCallback((at: number, state: FrameState, grid: CellLab | null) => {
    const s = store.current;
    if (!s.lockReady || s.locking) return;
    s.tailAt = at;
    if (grid) s.tail = [...trimTail(s.tail, at), { at, state, grid }];
  }, []);
  const recordingRef = useRef({ recording, measuring });
  useEffect(() => {
    recordingRef.current = { recording, measuring };
  }, [recording, measuring]);
  const regionsRef = useRef(regions);
  useEffect(() => {
    regionsRef.current = regions;
  }, [regions]);
  // 단계가 바뀌면 앞 단계 사진을 버린다
  useEffect(() => {
    store.current.tail = [];
  }, [step, runId]);

  useFaceFrame((frame: FaceFrame | null) => {
    const s = store.current;
    const requiredRegions = regionsRef.current;
    const regionsTracked =
      !!frame &&
      (frame.trackingState === "tracking" ||
        (frame.trackingState === "degraded" &&
          requiredRegions.length > 0 &&
          requiredRegions.every((region) => frame.usableRegions?.includes(region))));
    if (!frame || !regionsTracked) {
      if (s.collector)
        setStatus((prev) => (prev.front === false ? prev : { ...prev, front: false }));
      return;
    }
    const rec = recordingRef.current;
    const video = videoRef.current;
    const at = performance.now();
    // 잠근 카메라 설정으로 찍은 사진만 남긴다. 게이지가 재는 동안은 그쪽이 읽은 사진을 받는다
    if (
      rec.recording &&
      !rec.measuring &&
      video &&
      sampler.current &&
      s.lockReady &&
      !s.locking &&
      at - s.tailAt >= FRAME_GAP_MS &&
      at - (frame.detectedAt ?? frame.timestamp) <= FRAME_STALE_MS
    ) {
      const pixels = read.current(video);
      const state = frameState(frame, pixels);
      record(
        at,
        state,
        state.faces === 1 && pixels
          ? readCells(pixels, frame.landmarks, sampler.current.cells)
          : null,
      );
    }
    const q = qualityOf(frame);
    const regionsVisible = requiredRegions.every((region) => isRegionInView(frame, region));
    const before = s.center.value;
    if (regionsVisible) s.center.push(q);
    const center = s.center.value;
    const collectable = regionsVisible && (center === null ? facing(q) : goodFrame(q, center));
    if (s.collector && performance.now() - shown.current > 500) {
      shown.current = performance.now();
      setStatus((prev) => ({
        ...prev,
        front: collectable,
        quality: { ...q, aspect: eyeAspect(frame) },
      }));
    }
    if (before === null && center !== null) setStatus((prev) => ({ ...prev, center }));
    const collector = s.collector;
    const now = performance.now();
    if (!collector || !video) return;
    if (!s.lockReady) {
      const track = videoTrack(video);
      if (track) startLock(s, video, track);
      return;
    }
    if (!regionsVisible || center === null || !sampler.current || s.locking) return;
    if (now - (frame.detectedAt ?? frame.timestamp) > FRAME_STALE_MS) return;
    if (!collector.wants(q, center, now)) return;
    const pixels = read.current(video);
    if (!pixels) return;
    const started = performance.now();
    collector.push(readCells(pixels, frame.landmarks, sampler.current.cells), now);
    const readMs = performance.now() - started;
    if (wantsWhite(s)) s.eyes.push(readEyePixels(pixels, frame.landmarks, sampler.current.eyes));
    if (collector.done) finish(s, collector);
    setStatus((prev) => ({
      ...prev,
      center,
      bare: s.bare,
      white: s.white,
      frames: collector.count,
      readMs,
    }));
  });

  /** 그 단계 시작 기준. 아직 없거나 모으지 못했으면 null */
  const stepBaseline = useCallback((i: number) => store.current.steps.get(i) ?? null, []);
  /**
   * 묶음 안 다음 단계(next)의 시작 기준을 「다음」을 누르기 직전 사진으로 잡는다.
   * 이미 있으면 그대로 두고, 사진이 모자라면 false라 준비 카드에서 따로 모은다
   */
  const takeNext = useCallback((next: number, makeup: string) => {
    const s = store.current;
    if (s.steps.has(next)) return true;
    const base = nextStartBaseline(s.tail, makeup, performance.now(), s.center.value);
    s.tail = [];
    if (!base) return false;
    s.steps.set(next, base);
    return true;
  }, []);
  /**
   * 지금 하위 단계의 끝 기준을 「다음」을 누르기 직전 사진으로 만든다. 모자라면 null이다.
   * 모은 사진은 지우지 않아 이어서 takeNext로 다음 단계 시작 기준을 만들 수 있다
   */
  const takeEnd = useCallback(
    (makeup: string) =>
      nextStartBaseline(store.current.tail, makeup, performance.now(), store.current.center.value),
    [],
  );
  /**
   * 기준 사진이 모이지 않을 때 쓴다. 그 사람 정면과 모으던 사진을 버리고 지금 자세에서 다시 모은다.
   * 정면 pitch가 한 번 정해지면 그 값에서 벗어난 자세는 계속 걸러지기 때문이다
   */
  const restart = useCallback(() => {
    const s = store.current;
    if (!s.collector) return;
    s.center = new FrontCenter();
    s.collector = new BaselineCollector();
    s.eyes = [];
    setStatus((prev) => ({ ...prev, center: null, front: null, frames: 0 }));
  }, []);
  return { status, stepBaseline, takeNext, takeEnd, record, sampler, restart };
}
