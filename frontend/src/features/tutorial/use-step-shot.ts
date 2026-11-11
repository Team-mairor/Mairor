"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  FRAME_STALE_MS,
  isRegionInView,
  landmarkMotion,
  mirroredRegionBox,
  snapMirrored,
  useCamera,
  useFaceFrame,
  type FaceFrame,
  type RegionName,
} from "@/features/face";
import type { StepPhoto } from "@/features/session";
import { useTimeout } from "@/lib/hooks/use-timeout";

/**
 * 얼굴이 잠깐 멈췄을 때 찍어 흔들림을 줄인다.
 * 프레임 사이 얼굴 점 평균 이동이 STILL_MOVE(눈 사이 거리 대비) 아래로 STILL_MS 동안 이어지면 찍고,
 * STILL_MAX_WAIT_MS가 지나면 움직이고 있어도 찍는다. 기기에서 보며 조절한다
 */
export const STILL_MOVE = 0.02;
export const STILL_MS = 300;
export const STILL_MAX_WAIT_MS = 2500;
/** 프레임이 오지 않거나 추적이 끊겨도 기다림이 끝나도록 거는 대비 시간 */
export const SHOT_FALLBACK_MS = STILL_MAX_WAIT_MS + 500;

/** idle: 대기 없음 · waiting: 멈추기를 기다림 · outOfView: 찍을 부위가 화면 밖 · failed: 못 찍음 */
export type ShotState = "idle" | "waiting" | "outOfView" | "failed";

// 얼굴 전체(faceOval)는 가까이 가면 늘 잘려 보지 않는다
const inView = (frame: FaceFrame, regions: readonly RegionName[]) =>
  regions.every((r) => r === "faceOval" || isRegionInView(frame, r));

// 렌더 프레임이 아니라 실제 검출 시각으로 본다. 추론이 밀린 옛 좌표로 지금 영상을 자르지 않게
const isFresh = (frame: FaceFrame, now: number) =>
  now - (frame.detectedAt ?? frame.timestamp) <= FRAME_STALE_MS;

/** 상단 단계 바로 갈 수 있는 마지막 단계. 사진 없이 앞으로 건너뛰지 않게 처음으로 사진이 없는 단계까지 */
export function reachableStep(stepIds: readonly string[], hasPhoto: (stepId: string) => boolean) {
  const i = stepIds.findIndex((id) => !hasPhoto(id));
  return i === -1 ? stepIds.length - 1 : i;
}

/**
 * 단계 사진 한 장을 찍는다. start로 기다리기 시작해, 부위가 보이고 얼굴이 멈추면 onShot을 부른다.
 * 추적이 끊기거나 프레임이 오래됐거나 부위가 잘린 채로는 찍지 않고 failed가 된다.
 */
export function useStepShot(regions: readonly RegionName[], onShot: (photo: StepPhoto) => void) {
  const { videoRef } = useCamera();
  const timer = useTimeout();
  const [state, setState] = useState<ShotState>("idle");
  const frameRef = useRef<FaceFrame | null>(null);
  const stillSince = useRef<number | null>(null);
  // 기다리기 시작한 시각. 기다리는 중이 아니면 null
  const waitFrom = useRef<number | null>(null);
  // 타이머·프레임 콜백이 걸어 둔 때의 값이 아니라 지금 단계의 부위·콜백을 쓰게 한다
  const latest = useRef({ regions, onShot });
  useEffect(() => {
    latest.current = { regions, onShot };
  });

  const shoot = () => {
    if (waitFrom.current === null) return;
    waitFrom.current = null;
    timer.clear();
    const { regions, onShot } = latest.current;
    const frame = frameRef.current;
    // 찍을 부위를 모르면(기본 가이드를 못 불러옴 등) 확인 없이 찍지 않는다
    const ok =
      regions.length > 0 &&
      frame?.trackingState === "tracking" &&
      isFresh(frame, performance.now()) &&
      inView(frame, regions);
    const url = ok ? snapMirrored(videoRef.current) : null;
    if (!frame || !url) return setState("failed");
    setState("idle");
    onShot({ url, box: mirroredRegionBox(frame, regions) });
  };

  useFaceFrame((frame) => {
    const prev = frameRef.current;
    frameRef.current = frame;
    const now = performance.now();
    if (prev && frame && landmarkMotion(prev, frame) < STILL_MOVE) stillSince.current ??= now;
    else stillSince.current = null;
    if (waitFrom.current === null) return;
    // 추적이 끊긴 동안은 대비 타이머가 끝나면 failed로 떨어진다
    if (frame?.trackingState !== "tracking") return;
    if (!inView(frame, latest.current.regions)) {
      // 부위가 보일 때부터 다시 기다린다. 사용자는 촬영 취소로 대기를 접을 수 있다
      setState("outOfView");
      waitFrom.current = now;
      timer.set(shoot, SHOT_FALLBACK_MS);
      return;
    }
    setState("waiting");
    const still = stillSince.current !== null && now - stillSince.current >= STILL_MS;
    if (still || now - waitFrom.current >= STILL_MAX_WAIT_MS) shoot();
  });

  const start = () => {
    waitFrom.current = performance.now();
    setState("waiting");
    timer.set(shoot, SHOT_FALLBACK_MS);
  };
  const cancel = useCallback(() => {
    waitFrom.current = null;
    timer.clear();
    setState("idle");
  }, [timer]);

  return { state, shooting: state === "waiting" || state === "outOfView", start, cancel };
}
