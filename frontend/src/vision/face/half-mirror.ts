"use client";

import { LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER } from "./regions";
import type { FaceFrame, ViewTransform } from "./types";

/** 하프미러 계산에 필요한 얼굴 정보. eyes가 있으면 한쪽 눈을 감았을 때 뜬 눈 기준으로 그린다 */
export type MirrorFace = Pick<FaceFrame, "landmarks" | "imageSize"> &
  Partial<Pick<FaceFrame, "eyes">>;

/** 본인 기준 눈 */
export type EyeSide = "left" | "right";

// 갤럭시탭 S6 세로·카메라 위쪽 기준. 남는 오차는 /mirror-fit에서 맞춘다.
/** 화면 짧은 변 실제 길이 (1600px ÷ 286ppi) */
const SCREEN_SHORT_MM = 142;
/** 화면 위 가장자리에서 전면 카메라 중심까지 (자로 잰 값) */
const CAMERA_ABOVE_MM = 7;
/** 평균 눈 사이(mm). 사람마다 다른 만큼은 맞춤 배율로 메운다 */
const IOD_MM = 63;
/** 전면 카메라 가로 화각(세로 배치). 깊이 보정에만 쓴다 */
const CAMERA_HFOV_DEG = 45;
/** 정규화 z 1이 눈까지 거리의 몇 배인지 (영상 폭 ÷ 초점거리) */
const DEPTH_PER_Z = 2 * Math.tan((CAMERA_HFOV_DEG * Math.PI) / 360);

/** MediaPipe z 반영 비율. 위에서 내려다봐 z가 크게 나와 일부만 쓴다 */
const DEPTH_GAIN = 0.75;

/**
 * 눈보다 아래일수록 더하는 깊이(세로 거리 대비). 가이드를 보는 거리(눈–화면 23~32cm) 정답 찍기 6회에
 * 맞춘 값으로, 아래쪽을 조금 가깝게 본다
 */
const DEPTH_TILT = -0.3;

/** 화면 위 카메라 위치(요소 px)와 1mm가 요소에서 몇 px인지 */
export interface MirrorScreen {
  originX: number;
  originY: number;
  pxPerMm: number;
}

/** 맞춤 보정. 화면 mm 좌표(카메라 원점)에 scale을 곱하고 dx·dy를 더한다 */
export interface MirrorFit {
  scale: number;
  dx: number;
  dy: number;
  /** 맞출 때 뜬 눈(주로 쓰는 눈). 없으면 두 눈 가운데에서 본다고 보고, 눈을 바꿔도 따라가지 않는다 */
  eye?: EyeSide;
  /** 저장한 시각(ms). 다른 사람이 맞춘 값인지 알아보게 보여 준다 */
  savedAt?: number;
}

const NO_FIT: MirrorFit = { scale: 1, dx: 0, dy: 0 };
const FIT_KEY = "mairor-mirror-fit";

/**
 * 요소 기준 화면 위 카메라 위치. 뷰포트가 상태바·주소창만큼 내려와 있다고 본다.
 * 아래 내비게이션 바가 있으면 몇 mm 어긋나고, 맞춤 보정이 메운다
 */
export function mirrorScreen(el: HTMLElement): MirrorScreen {
  const rect = el.getBoundingClientRect();
  // html의 zoom(globals.css) 때문에 뷰포트 px와 요소 안 px가 다르다
  const zoom = rect.width / el.clientWidth || 1;
  const pxPerMm = Math.min(screen.width, screen.height) / SCREEN_SHORT_MM;
  const camX = window.innerWidth / 2;
  const camY = -(screen.height - window.innerHeight) - CAMERA_ABOVE_MM * pxPerMm;
  return {
    originX: (camX - rect.left) / zoom,
    originY: (camY - rect.top) / zoom,
    pxPerMm: pxPerMm / zoom,
  };
}

/** 눈꺼풀 위·아래와 눈 양 끝 점 (본인 기준) */
const LIDS: Record<EyeSide, [number, number, number, number]> = {
  right: [159, 145, 33, 133],
  left: [386, 374, 362, 263],
};
/**
 * 한쪽 눈만 감았다고 볼 때 두 눈 뜬 정도의 비. 깜빡임 점수는 한쪽을 감으면 뜬 눈도 함께 올라가
 * (고개를 숙이면 둘 다 감은 것으로 나온다) 눈꺼풀 사이 거리를 눈 폭으로 나눠 두 눈을 비교한다
 */
const WINK_RATIO = 1.35;

function eyeOpening(frame: MirrorFace, side: EyeSide) {
  const { width: w, height: h } = frame.imageSize;
  const [up, down, a, b] = LIDS[side].map((i) => frame.landmarks[i]);
  const gap = Math.hypot((up.x - down.x) * w, (up.y - down.y) * h);
  return gap / Math.max(1e-6, Math.hypot((a.x - b.x) * w, (a.y - b.y) * h));
}

/** 한쪽 눈만 뜨고 있으면 그 눈, 두 눈 다 뜨거나 감았으면 null */
export function openEye(frame: MirrorFace): EyeSide | null {
  const right = eyeOpening(frame, "right");
  const left = eyeOpening(frame, "left");
  if (right > left * WINK_RATIO) return "right";
  if (left > right * WINK_RATIO) return "left";
  return null;
}

/**
 * 지금 보고 있는 눈. 한쪽만 감았으면 뜬 눈, 아니면 맞출 때 쓴 눈이다.
 * 두 눈 사이가 6cm 남짓이라, 보는 눈이 바뀌면 비친 자리가 3cm 가까이 옆으로 옮겨진다
 */
export function viewingEye(frame: MirrorFace, fit: MirrorFit): EyeSide | null {
  if (!fit.eye) return null;
  return openEye(frame) ?? fit.eye;
}

/** 한쪽 눈 감음이 이만큼(ms) 이어져야 뜬 눈으로 바꾼다. 깜빡일 때 잠깐 한쪽만 감긴 것으로 잡혀 상이 튀지 않게 한다 */
const WINK_HOLD_MS = 400;
/** 두 눈을 다시 뜬 뒤 이만큼(ms) 지나면 맞출 때 쓴 눈으로 돌아간다 */
const WINK_RELEASE_MS = 150;

/** 보는 눈을 시간으로 거른다. 섀도처럼 한쪽 눈을 감고 바를 때만 뜬 눈으로 바꾼다 */
export class EyeHold {
  private seen: EyeSide | null = null;
  private since = 0;
  private shown: EyeSide | null = null;

  update(open: EyeSide | null, now: number): EyeSide | null {
    if (open !== this.seen) {
      this.seen = open;
      this.since = now;
    }
    if (now - this.since >= (open ? WINK_HOLD_MS : WINK_RELEASE_MS)) this.shown = open;
    return this.shown;
  }
}

const eyeHold = new EyeHold();

/** 화면에 그릴 때 보는 눈. 깜빡임처럼 짧게 한쪽만 감긴 것은 무시한다 */
function heldViewingEye(frame: MirrorFace, fit: MirrorFit): EyeSide | null {
  if (!fit.eye) return null;
  return eyeHold.update(openEye(frame), performance.now()) ?? fit.eye;
}

/** 보는 눈 위치(정규화 좌표). null이면 두 눈 가운데 */
function eyePoint(frame: MirrorFace, eye: EyeSide | null) {
  const a = frame.landmarks[RIGHT_IRIS_CENTER];
  const b = frame.landmarks[LEFT_IRIS_CENTER];
  if (eye === "right") return { x: a.x, y: a.y, z: a.z ?? 0 };
  if (eye === "left") return { x: b.x, y: b.y, z: b.z ?? 0 };
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: ((a.z ?? 0) + (b.z ?? 0)) / 2 };
}

/**
 * 거울에 비친 얼굴 위치로 그릴 프레임과 변환. 점 P를 눈 E에서 본 시선은 화면을
 * (E·Zp + P·Ze) / (Ze + Zp)에서 지난다(Z는 화면까지 거리). 눈 깊이의 점은 (E + P) / 2라 변환 하나로 그리고,
 * 깊이가 다른 점은 같은 변환에서 맞는 자리에 오도록 얼굴 점을 옮긴다
 */
export function halfMirror<F extends MirrorFace>(
  frame: F,
  screen: MirrorScreen,
  fit: MirrorFit = NO_FIT,
  depthGain = DEPTH_GAIN,
  depthTilt = DEPTH_TILT,
  /** 보는 눈. 정하지 않으면 깜빡임을 거른 지금 보는 눈이다 */
  viewer: EyeSide | null = heldViewingEye(frame, fit),
): { frame: F; view: ViewTransform } {
  const { width: w, height: h } = frame.imageSize;
  const eye = eyePoint(frame, viewer);
  // 영상 가운데 기준으로 눈 깊이에 있다고 보면 P0, 실제 깊이 비 r = Zp / Ze이면 P = r·P0.
  // 변환이 (E + P') / 2로 그리므로 P' = 2·r·(E + P0) / (1 + r) - E = ((r - 1)·E + 2r·P0) / (1 + r)
  const landmarks = frame.landmarks.map((p) => {
    // 세로 거리는 z와 같은 축척(영상 폭 기준)으로 바꿔 더한다
    const depth = ((p.z ?? 0) - eye.z) * depthGain + ((p.y - eye.y) * h * depthTilt) / w;
    const r = 1 + depth * DEPTH_PER_Z;
    const shift = (v: number, e: number) =>
      0.5 + ((r - 1) * (e - 0.5) + 2 * r * (v - 0.5)) / (1 + r);
    return { x: shift(p.x, eye.x), y: shift(p.y, eye.y), z: p.z };
  });
  const base = eyePoint(frame, fit.eye ?? null);
  return { frame: { ...frame, landmarks }, view: eyeDepthTransform(frame, screen, fit, eye, base) };
}

/** 눈 깊이에서 영상 1px이 실제로 몇 mm인지. 눈 사이 거리를 IOD_MM으로 보고 잰다 */
function mmPerPx(frame: MirrorFace) {
  const { width: w, height: h } = frame.imageSize;
  const a = frame.landmarks[RIGHT_IRIS_CENTER];
  const b = frame.landmarks[LEFT_IRIS_CENTER];
  // 고개를 돌려도 줄지 않게 깊이까지 넣어 잰다 (z는 x와 같은 축척)
  const iod = Math.hypot((a.x - b.x) * w, (a.y - b.y) * h, ((a.z ?? 0) - (b.z ?? 0)) * w);
  return IOD_MM / Math.max(1, iod);
}

/** 눈에서 화면까지 거리(mm). 화각·평균 눈 사이 가정에 비례해 틀린다 */
export function eyeDistanceMm(frame: MirrorFace) {
  return (frame.imageSize.width / DEPTH_PER_Z) * mmPerPx(frame);
}

/** 눈과 같은 깊이의 점을 비친 자리에 그리는 변환 */
function eyeDepthTransform(
  frame: MirrorFace,
  screen: MirrorScreen,
  fit: MirrorFit,
  eye: { x: number; y: number },
  base: { x: number; y: number },
): ViewTransform {
  const { width: w, height: h } = frame.imageSize;
  const k = mmPerPx(frame);
  // 카메라 기준 실제 위치(mm). 보는 방향으로 x 오른쪽·y 아래, 영상은 좌우 반대라 x를 뒤집는다
  const toMm = (p: { x: number; y: number }) => ({
    x: (w / 2 - p.x * w) * k,
    y: (p.y * h - h / 2) * k,
  });
  // 맞출 때 쓴 눈(base)까지는 맞춤 배율을 함께 곱하고, 다른 눈으로 바꾼 만큼은 실제 거리 그대로 옮긴다.
  // 배율은 눈 사이보다 거리 추정 오차를 메우는 쪽이라, 눈을 바꿀 때 곱하면 그만큼 더 옮겨진다
  const e = toMm(base);
  const v = toMm(eye);
  // 반전 영상 좌표 u = w - x에서 P = ((u - w/2)k, (y - h/2)k). 화면 mm = scale·(E + P)/2 + d
  const half = (fit.scale * k) / 2;
  const x0 = (fit.scale * e.x + (v.x - e.x)) / 2 - (half * w) / 2 + fit.dx;
  const y0 = (fit.scale * e.y + (v.y - e.y)) / 2 - (half * h) / 2 + fit.dy;
  return {
    scale: half * screen.pxPerMm,
    offsetX: screen.originX + x0 * screen.pxPerMm,
    offsetY: screen.originY + y0 * screen.pxPerMm,
    mirrored: true,
  };
}

type Px = { x: number; y: number };

/**
 * 보정 없이 계산한 두 눈 가운데(predicted)를 맞춘 자리(seen)로 옮기는 보정. scale은 맞춘 간격 배율,
 * eye는 맞출 때 뜬 눈으로 predicted도 그 눈 기준으로 계산했어야 한다
 */
export function fitMirror(
  predicted: Px,
  seen: Px,
  screen: MirrorScreen,
  scale = 1,
  eye?: EyeSide,
): MirrorFit {
  const mm = (p: Px) => ({
    x: (p.x - screen.originX) / screen.pxPerMm,
    y: (p.y - screen.originY) / screen.pxPerMm,
  });
  const p = mm(predicted);
  const s = mm(seen);
  return { scale, dx: s.x - scale * p.x, dy: s.y - scale * p.y, ...(eye && { eye }) };
}

let cachedFit: MirrorFit | null = null;

/** 저장된 맞춤 보정. 없거나 읽지 못하면 보정 없음 */
export function loadMirrorFit(): MirrorFit {
  if (cachedFit) return cachedFit;
  try {
    const saved = JSON.parse(localStorage.getItem(FIT_KEY) ?? "null") as MirrorFit | null;
    const valid =
      saved &&
      Number.isFinite(saved.scale) &&
      saved.scale > 0 &&
      Number.isFinite(saved.dx) &&
      Number.isFinite(saved.dy);
    cachedFit = valid
      ? {
          ...saved,
          eye: saved.eye === "left" || saved.eye === "right" ? saved.eye : undefined,
          savedAt: Number.isFinite(saved.savedAt) ? saved.savedAt : undefined,
        }
      : NO_FIT;
  } catch {
    cachedFit = NO_FIT;
  }
  return cachedFit;
}

/** 거울 맞추기로 저장한 보정이 있는지 */
export const hasMirrorFit = () => loadMirrorFit() !== NO_FIT;

/** 맞춤 보정을 저장한다. null이면 지운다 */
export function saveMirrorFit(fit: MirrorFit | null) {
  if (fit) fit = { ...fit, savedAt: Date.now() };
  cachedFit = fit ?? NO_FIT;
  try {
    if (fit) localStorage.setItem(FIT_KEY, JSON.stringify(fit));
    else localStorage.removeItem(FIT_KEY);
  } catch {
    // 저장에 실패해도 이번 실행에는 적용된다
  }
}
