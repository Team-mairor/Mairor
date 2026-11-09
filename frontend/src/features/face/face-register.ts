"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useCamera, useFaceFrame } from "./camera-provider";
import { faceWidthRatio, MIN_FACE_WIDTH_RATIO } from "./tracking-issue";
import { KEY_REGIONS } from "./tracking-rules";
import type { FaceFrame, RegionName } from "./types";
import { MIN_IN_FRAME_RATIO } from "./visibility";

/** 얼굴 등록 필수 촬영 조건. 모달에 표시하는 순서와 같다 */
export const CHECKS = ["light", "distance", "front", "clear"] as const;
export type CheckName = (typeof CHECKS)[number];
export type FaceCheck = Record<CheckName, boolean>;

export const NO_CHECK: FaceCheck = { light: false, distance: false, front: false, clear: false };
const ALL_PASSED: FaceCheck = { light: true, distance: true, front: true, clear: true };

// 거리·가운데·위아래 기준은 원 표시 방식과 하프미러 보정이 정해지면 확정할 임시값이다.
/** 얼굴 폭 / 영상 폭이 이 범위면 적정 거리. 너무 멀면 색이 부정확하고, 너무 가까우면 얼굴이 잘린다 */
const DISTANCE = { min: MIN_FACE_WIDTH_RATIO, max: 0.9 };
/** 얼굴 중심이 영상 가운데에서 이 비율 안에 있어야 원 안으로 본다 */
const CENTER_TOLERANCE = 0.15;
/** 정면으로 보는 좌우·위아래 각도 (라디안, 약 11도). 평소 3도 안팎, 살짝 돌리면 17도 이상 */
const MAX_FRONT_ANGLE = 0.2;
/** 정면으로 보는 기울기 (라디안, 약 9도). 평소 4도 이하, 갸웃하면 12도 이상 */
const MAX_ROLL = 0.15;
/**
 * 얼굴 가운데 평균 밝기 (0~255). 평소 135~185, 어두운 방 60~70.
 * 자동 노출 때문에 강한 빛에서도 평균이 크게 오르지 않아 상한은 안전장치로만 둔다
 */
const BRIGHTNESS = { min: 100, max: 215 };
/** 밝기는 영상을 읽어야 해서 매 프레임 대신 이 간격(ms)마다 잰다 */
const BRIGHTNESS_EVERY_MS = 250;
/** 기준 근처에서 한두 프레임 흔들려도 통과를 이만큼(ms) 유지해, 유지 시간을 처음부터 다시 재지 않는다 */
const PASS_GRACE_MS = 300;
/** 가림 판정에 쓰는 부위. 핵심 부위와 얼굴 윤곽이 모두 보여야 한다 */
const CLEAR_REGIONS: readonly RegionName[] = [...KEY_REGIONS, "faceOval"];

/** 지금 프레임이 필수 촬영 조건을 각각 만족하는지. 밝기를 아직 못 쟀으면 null */
export function checkFace(frame: FaceFrame | null, brightness: number | null): FaceCheck {
  if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold") return NO_CHECK;
  const box = faceBox(frame);
  const centerX = (box.minX + box.maxX) / 2;
  const centerY = (box.minY + box.maxY) / 2;
  const ratio = faceWidthRatio(frame);
  return {
    light: brightness !== null && brightness >= BRIGHTNESS.min && brightness <= BRIGHTNESS.max,
    distance:
      ratio >= DISTANCE.min &&
      ratio <= DISTANCE.max &&
      Math.abs(centerX - 0.5) <= CENTER_TOLERANCE &&
      Math.abs(centerY - 0.5) <= CENTER_TOLERANCE,
    front:
      Math.abs(frame.pose.yaw) <= MAX_FRONT_ANGLE &&
      Math.abs(frame.pose.pitch) <= MAX_FRONT_ANGLE &&
      Math.abs(frame.pose.roll) <= MAX_ROLL,
    // 손 같은 가림은 랜드마크만으로는 알 수 없어, 부위가 모두 화면 안에 정면으로 보이는지만 본다
    clear:
      frame.trackingState === "tracking" &&
      CLEAR_REGIONS.every((name) => {
        const v = frame.regionVisibility[name];
        return v.facing && v.inFrameRatio >= MIN_IN_FRAME_RATIO;
      }),
  };
}

/** 거리·위치가 기준을 벗어난 쪽. 좌우·위아래는 거울처럼 뒤집어 보여 주는 화면 기준이다 */
export type DistanceHint = "closer" | "back" | "left" | "right" | "up" | "down";

export const DISTANCE_HINT_TEXT: Record<DistanceHint, string> = {
  closer: "조금 더 가까이 와 주세요",
  back: "조금 뒤로 물러나 주세요",
  left: "얼굴을 왼쪽으로 조금 옮겨 주세요",
  right: "얼굴을 오른쪽으로 조금 옮겨 주세요",
  up: "얼굴을 조금 위로 올려 주세요",
  down: "얼굴을 조금 아래로 내려 주세요",
};

/** 적정 거리 조건(checkFace의 distance)을 어떻게 맞추면 되는지. 맞거나 얼굴이 없으면 null */
export function distanceHint(frame: FaceFrame | null): DistanceHint | null {
  if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold") return null;
  const ratio = faceWidthRatio(frame);
  if (ratio < DISTANCE.min) return "closer";
  if (ratio > DISTANCE.max) return "back";
  const box = faceBox(frame);
  // 영상은 원본 좌표라, 거울처럼 뒤집어 보여 주는 화면에서는 x를 뒤집어 본다
  const x = 1 - (box.minX + box.maxX) / 2;
  const y = (box.minY + box.maxY) / 2;
  if (x - 0.5 > CENTER_TOLERANCE) return "left";
  if (0.5 - x > CENTER_TOLERANCE) return "right";
  if (y - 0.5 > CENTER_TOLERANCE) return "up";
  if (0.5 - y > CENTER_TOLERANCE) return "down";
  return null;
}

/** 적정 거리의 최소 얼굴 폭 비율 (얼굴 폭 / 영상 폭). 원 안에 목표 크기를 그릴 때 쓴다 */
export const MIN_DISTANCE_RATIO = DISTANCE.min;

export function allPassed(check: FaceCheck) {
  return CHECKS.every((name) => check[name]);
}

/** 한쪽 눈이라도 감았는지. 깜빡임은 자연스러워 조건으로 두지 않고, 찍는 순간에만 본다 */
export function eyesClosed(frame: FaceFrame | null) {
  return !!frame && (frame.eyes.left.blinking || frame.eyes.right.blinking);
}

/**
 * 얼굴 등록 화면이 열려 있는 동안 촬영 조건을 실시간으로 판정한다. 결과가 바뀔 때만 다시 그린다.
 * frame은 마지막 프레임, passedNow는 유예 없이 마지막 프레임이 조건을 모두 통과하는지로, 찍는 순간에 쓴다
 */
export function useFaceCheck(enabled: boolean) {
  const { videoRef } = useCamera();
  const [check, setCheck] = useState(NO_CHECK);
  /** 얼굴이 잡혔는지. 바뀔 때만 다시 그린다 */
  const [found, setFound] = useState(false);
  /** 거리·위치를 어떻게 맞추면 되는지 */
  const [hint, setHint] = useState<DistanceHint | null>(null);
  const frameRef = useRef<FaceFrame | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const brightness = useRef<number | null>(null);
  const measuredAt = useRef(-Infinity);
  const passedAt = useRef(-Infinity);

  // 켜고 끌 때마다 비운다. 카메라 오류로 프레임이 끊겨도 지난 판정으로 촬영하지 않게 한다
  const [prevEnabled, setPrevEnabled] = useState(enabled);
  if (enabled !== prevEnabled) {
    setPrevEnabled(enabled);
    setCheck(NO_CHECK);
    setFound(false);
    setHint(null);
  }
  useEffect(() => {
    frameRef.current = null;
    brightness.current = null;
    measuredAt.current = -Infinity;
    passedAt.current = -Infinity;
  }, [enabled]);

  useFaceFrame((frame) => {
    if (!enabled) return;
    frameRef.current = frame;
    const video = videoRef.current;
    const now = performance.now();
    const tracked = frame?.trackingState === "tracking" || frame?.trackingState === "degraded";
    if (frame && tracked && video && now - measuredAt.current >= BRIGHTNESS_EVERY_MS) {
      measuredAt.current = now;
      canvasRef.current ??= document.createElement("canvas");
      brightness.current = faceBrightness(video, frame, canvasRef.current);
    }
    setFound(tracked);
    setHint(distanceHint(frame));
    let next = checkFace(frame, brightness.current);
    if (allPassed(next)) passedAt.current = now;
    else if (now - passedAt.current < PASS_GRACE_MS) next = ALL_PASSED;
    setCheck((prev) => (CHECKS.every((name) => prev[name] === next[name]) ? prev : next));
  });

  const passedNow = useCallback(
    () => allPassed(checkFace(frameRef.current, brightness.current)),
    [],
  );

  return { check, found, hint, frame: frameRef, passedNow };
}

/** 지금 영상을 원본 그대로(좌우 반전 없이) 한 장 찍는다 */
export function captureFace(video: HTMLVideoElement): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d")!.drawImage(video, 0, 0);
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("얼굴 사진을 만들지 못했습니다"))),
      "image/jpeg",
      0.9,
    ),
  );
}

export { clearFacePhoto, facePhoto, saveFacePhoto } from "./registered-photo";

interface Box {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

/** 얼굴 랜드마크를 감싸는 상자 (원본 영상 기준 0~1) */
export function faceBox(frame: FaceFrame): Box {
  const box = { minX: 1, minY: 1, maxX: 0, maxY: 0 };
  for (const p of frame.landmarks) {
    box.minX = Math.min(box.minX, p.x);
    box.minY = Math.min(box.minY, p.y);
    box.maxX = Math.max(box.maxX, p.x);
    box.maxY = Math.max(box.maxY, p.y);
  }
  return box;
}

const SAMPLE = 16;
// 머리카락·배경이 섞이지 않게 얼굴 상자의 가운데만 본다
const INSET = 0.25;

/** 얼굴 가운데의 평균 밝기 (0~255) */
function faceBrightness(
  video: HTMLVideoElement,
  frame: FaceFrame,
  canvas: HTMLCanvasElement,
): number | null {
  const { videoWidth: w, videoHeight: h } = video;
  const box = faceBox(frame);
  const dx = (box.maxX - box.minX) * INSET;
  const dy = (box.maxY - box.minY) * INSET;
  const x = Math.max(0, box.minX + dx) * w;
  const y = Math.max(0, box.minY + dy) * h;
  const sw = Math.min(w, (box.maxX - dx) * w) - x;
  const sh = Math.min(h, (box.maxY - dy) * h) - y;
  if (sw < 1 || sh < 1) return null;
  // 크기를 다시 넣으면 캔버스를 새로 잡으므로 처음 한 번만 정한다
  if (canvas.width !== SAMPLE) {
    canvas.width = SAMPLE;
    canvas.height = SAMPLE;
  }
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(video, x, y, sw, sh, 0, 0, SAMPLE, SAMPLE);
  const { data } = ctx.getImageData(0, 0, SAMPLE, SAMPLE);
  let sum = 0;
  for (let i = 0; i < data.length; i += 4) {
    sum += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  }
  return sum / (SAMPLE * SAMPLE);
}
