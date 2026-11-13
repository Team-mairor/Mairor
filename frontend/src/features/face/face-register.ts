"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { isMirror } from "@/lib/mirror";

import { useCamera, useFaceFrame } from "./camera-provider";
import { halfMirror, loadMirrorFit, mirrorScreen } from "./half-mirror";
import { faceWidthRatio, MIN_FACE_WIDTH_RATIO } from "./tracking-issue";
import { KEY_REGIONS } from "./tracking-rules";
import type { FaceFrame, RegionName } from "./types";
import { toScreen } from "./view-transform";
import { MIN_IN_FRAME_RATIO } from "./visibility";

/** 얼굴 등록 필수 촬영 조건. 모달에 표시하는 순서와 같다 */
export const CHECKS = ["light", "distance", "front", "clear"] as const;
export type CheckName = (typeof CHECKS)[number];
export type FaceCheck = Record<CheckName, boolean>;

export const NO_CHECK: FaceCheck = { light: false, distance: false, front: false, clear: false };
const ALL_PASSED: FaceCheck = { light: true, distance: true, front: true, clear: true };

// 거리·가운데·위아래 기준은 하프미러 실측 전 임시값이다.
/** 얼굴 폭 / 영상 폭이 이 범위면 적정 거리. 너무 멀면 색이 부정확하고, 너무 가까우면 얼굴이 잘린다 */
const DISTANCE = { min: MIN_FACE_WIDTH_RATIO, max: 0.9 };
/**
 * 미러필름 위 최소 비율. 비친 얼굴을 원에 맞추면 얼굴이 카메라보다 아래에 와서, 가까이 갈수록 카메라에 잘린다.
 * 조금 물러나도 등록 사진으로 조명·색을 재기에는 충분하다
 */
const MIRROR_MIN_RATIO = 0.3;
const minRatio = () => (isMirror() ? MIRROR_MIN_RATIO : DISTANCE.min);
/**
 * 얼굴 중심이 가운데에서 이 비율 안에 있어야 원 안으로 본다.
 * 원이 있으면 원 지름, 없으면 영상 크기 대비 (faceOffset)
 */
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

/**
 * 지금 프레임이 필수 촬영 조건을 각각 만족하는지. 밝기를 아직 못 쟀으면 null.
 * circle은 얼굴 원 요소로, 미러필름 위에서 비친 얼굴이 원 안에 있는지 볼 때 쓴다
 */
export function checkFace(
  frame: FaceFrame | null,
  brightness: number | null,
  circle: HTMLElement | null = null,
): FaceCheck {
  if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold") return NO_CHECK;
  const offset = faceOffset(frame, circle);
  const ratio = faceWidthRatio(frame);
  return {
    light: brightness !== null && brightness >= BRIGHTNESS.min && brightness <= BRIGHTNESS.max,
    distance:
      ratio >= minRatio() &&
      ratio <= DISTANCE.max &&
      Math.abs(offset.x) <= CENTER_TOLERANCE &&
      Math.abs(offset.y) <= CENTER_TOLERANCE,
    front:
      Math.abs(frame.pose.yaw) <= MAX_FRONT_ANGLE &&
      Math.abs(frame.pose.pitch) <= MAX_FRONT_ANGLE &&
      Math.abs(frame.pose.roll) <= MAX_ROLL,
    // 손 같은 가림은 랜드마크만으로는 알 수 없어, 부위가 모두 화면 안에 정면으로 보이는지만 본다.
    // 미러필름 위에서는 화장할 때와 같은 자리에서 찍도록 튜토리얼처럼 추적이 안정적인지만 본다.
    // 비친 얼굴을 원에 맞추면 얼굴이 카메라보다 아래에 와 턱이 잘리기 쉬운데, 거울로는 보이지 않는다
    clear:
      frame.trackingState === "tracking" &&
      (isMirror() ||
        CLEAR_REGIONS.every((name) => {
          const v = frame.regionVisibility[name];
          return v.facing && v.inFrameRatio >= MIN_IN_FRAME_RATIO;
        })),
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

/**
 * 적정 거리 조건(checkFace의 distance)을 어떻게 맞추면 되는지. 맞거나 얼굴이 없으면 null.
 * 비친 얼굴은 거리와 상관없이 실제 크기의 절반이라, 미러필름 위에서도 가까이·뒤로는 카메라 영상으로 본다
 */
export function distanceHint(
  frame: FaceFrame | null,
  circle: HTMLElement | null = null,
): DistanceHint | null {
  if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold") return null;
  const ratio = faceWidthRatio(frame);
  if (ratio < minRatio()) return "closer";
  if (ratio > DISTANCE.max) return "back";
  const { x, y } = faceOffset(frame, circle);
  if (x > CENTER_TOLERANCE) return "left";
  if (-x > CENTER_TOLERANCE) return "right";
  if (y > CENTER_TOLERANCE) return "up";
  if (-y > CENTER_TOLERANCE) return "down";
  return null;
}

/**
 * 얼굴 중심이 가운데에서 벗어난 정도. 거울처럼 보는 화면 기준으로 x는 오른쪽, y는 아래가 +다.
 * 원이 있으면 원 안에 그리는 얼굴(faceBoxIn)이 원 가운데에서 원 지름의 몇 배, 없으면 영상 가운데에서 영상 크기의 몇 배
 */
function faceOffset(frame: FaceFrame, circle: HTMLElement | null) {
  if (circle) {
    const box = faceBoxIn(frame, circle);
    const size = circle.clientWidth || 1;
    return { x: (box.minX + box.maxX) / 2 / size - 0.5, y: (box.minY + box.maxY) / 2 / size - 0.5 };
  }
  const box = faceBox(frame);
  // 영상은 원본 좌표라 x를 뒤집어 본다
  return { x: 0.5 - (box.minX + box.maxX) / 2, y: (box.minY + box.maxY) / 2 - 0.5 };
}

/**
 * 정사각형 얼굴 원(circle) 안 px로 본 얼굴 상자. 미러필름 위에서는 가이드·화장과 같은 변환(halfMirror)으로
 * 거울에 비친 얼굴 자리, 아니면 원 안 영상(가운데 정사각형을 좌우 반전) 자리다
 */
export function faceBoxIn(frame: FaceFrame, circle: HTMLElement): Box {
  const size = circle.clientWidth;
  const { width: w, height: h } = frame.imageSize;
  const side = Math.min(w, h);
  let toPx = (p: FaceFrame["landmarks"][number]) => ({
    x: size - ((p.x * w - (w - side) / 2) / side) * size,
    y: ((p.y * h - (h - side) / 2) / side) * size,
  });
  let { landmarks } = frame;
  if (isMirror()) {
    const reflected = halfMirror(frame, mirrorScreen(circle), loadMirrorFit());
    landmarks = reflected.frame.landmarks;
    toPx = (p) => toScreen(p, frame.imageSize, reflected.view);
  }
  const box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (const p of landmarks) {
    const { x, y } = toPx(p);
    box.minX = Math.min(box.minX, x);
    box.minY = Math.min(box.minY, y);
    box.maxX = Math.max(box.maxX, x);
    box.maxY = Math.max(box.maxY, y);
  }
  return box;
}

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
export function useFaceCheck(enabled: boolean, circleRef?: RefObject<HTMLElement | null>) {
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
    const circle = circleRef?.current ?? null;
    setHint(distanceHint(frame, circle));
    let next = checkFace(frame, brightness.current, circle);
    if (allPassed(next)) passedAt.current = now;
    else if (now - passedAt.current < PASS_GRACE_MS) next = ALL_PASSED;
    setCheck((prev) => (CHECKS.every((name) => prev[name] === next[name]) ? prev : next));
  });

  const passedNow = useCallback(
    () => allPassed(checkFace(frameRef.current, brightness.current, circleRef?.current ?? null)),
    [circleRef],
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

/** 지금 프레임을 화면·거울에서 보던 방향(좌우 반전)으로 찍은 JPEG data URL. 영상이 아직 없으면 null */
export function snapMirrored(video: HTMLVideoElement | null): string | null {
  if (!video?.videoWidth) return null;
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(-1, 1);
  ctx.drawImage(video, -canvas.width, 0);
  return canvas.toDataURL("image/jpeg", 0.85);
}

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
