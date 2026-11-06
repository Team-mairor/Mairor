import { LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER } from "./regions";
import type { FaceFrame, ViewTransform } from "./types";

// 갤럭시탭 S6 Lite 세로 기준 상수. 남는 오차는 하프미러 맞춤 화면(/mirror-fit)에서 사용자가 보정한다.
/** 화면 짧은 변 실제 길이 (1200px ÷ 224ppi) */
const SCREEN_SHORT_MM = 135.9;
/** 화면 위 가장자리에서 전면 카메라 중심까지 (위쪽 베젤 가운데) */
const CAMERA_ABOVE_MM = 5;
/** 두 홍채 중심 거리 평균. 사람마다 다른 만큼은 맞춤 배율이 메운다 */
const IOD_MM = 63;
/**
 * 전면 카메라 가로 화각(실측 전 추정). 얼굴 점의 앞뒤 깊이를 거리 비로 바꿀 때만 쓴다.
 * 10° 틀려도 코끝 위치가 1mm 남짓 달라질 뿐이다
 */
const CAMERA_HFOV_DEG = 66;
/** 정규화 z 1이 눈까지 거리의 몇 배인지. MediaPipe z는 x와 같은 축척이라 영상 폭 ÷ 초점거리 */
const DEPTH_PER_Z = 2 * Math.tan((CAMERA_HFOV_DEG * Math.PI) / 360);

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
}

const NO_FIT: MirrorFit = { scale: 1, dx: 0, dy: 0 };
const FIT_KEY = "mairor-mirror-fit";

/**
 * 요소(캔버스 등) 기준 화면 위 카메라 위치. 뷰포트는 화면 폭을 다 쓰고, 위쪽 상태바·주소창만큼 내려와 있다고 본다.
 * ponytail: 아래 내비게이션 바도 위쪽으로 셈해 몇 mm 어긋날 수 있다. 맞춤 화면의 이동 보정이 메운다
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

/**
 * 하프미러에 비친 얼굴 위치로 그릴 프레임과 변환. 렌더러에는 frame 대신 돌려준 frame을 넘긴다.
 * 화면이 곧 거울면이라, 점 P의 비친 상은 화면 뒤 같은 거리에 있고 두 눈 가운데 E에서 그 상을 보는 시선은
 * 화면을 (E·Zp + P·Ze) / (Ze + Zp)에서 지난다(Z는 화면까지 거리). 실제 크기(mm)는 IOD로 잰다.
 * 눈과 같은 깊이의 점은 (E + P) / 2라 영상 좌표에 대해 배율·이동뿐이므로 ViewTransform으로 나타내고,
 * 코끝·볼처럼 깊이가 다른 점은 같은 변환으로 맞는 자리에 가도록 얼굴 점을 옮겨 둔다.
 * 얼굴이 카메라보다 15cm쯤 아래라 옮기지 않으면 코끝이 6mm쯤 어긋난다.
 */
export function halfMirror(
  frame: FaceFrame,
  screen: MirrorScreen,
  fit: MirrorFit = NO_FIT,
): { frame: FaceFrame; view: ViewTransform } {
  const a = frame.landmarks[RIGHT_IRIS_CENTER];
  const b = frame.landmarks[LEFT_IRIS_CENTER];
  const eye = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: ((a.z ?? 0) + (b.z ?? 0)) / 2 };
  // 영상 가운데 기준으로 눈 깊이에 있다고 보면 P0, 실제 깊이 비 r = Zp / Ze이면 P = r·P0.
  // 변환이 (E + P') / 2로 그리므로 P' = 2·r·(E + P0) / (1 + r) - E = ((r - 1)·E + 2r·P0) / (1 + r)
  const landmarks = frame.landmarks.map((p) => {
    const r = 1 + ((p.z ?? 0) - eye.z) * DEPTH_PER_Z;
    const shift = (v: number, e: number) =>
      0.5 + ((r - 1) * (e - 0.5) + 2 * r * (v - 0.5)) / (1 + r);
    return { x: shift(p.x, eye.x), y: shift(p.y, eye.y), z: p.z };
  });
  return { frame: { ...frame, landmarks }, view: eyeDepthTransform(frame, screen, fit) };
}

/** 눈 깊이에서 영상 1px이 실제로 몇 mm인지. 눈 사이 거리를 IOD_MM으로 보고 잰다 */
function mmPerPx(frame: FaceFrame) {
  const { width: w, height: h } = frame.imageSize;
  const a = frame.landmarks[RIGHT_IRIS_CENTER];
  const b = frame.landmarks[LEFT_IRIS_CENTER];
  // 고개를 돌려도 줄지 않게 깊이까지 넣어 잰다 (z는 x와 같은 축척)
  const iod = Math.hypot((a.x - b.x) * w, (a.y - b.y) * h, ((a.z ?? 0) - (b.z ?? 0)) * w);
  return IOD_MM / Math.max(1, iod);
}

/**
 * 눈에서 화면까지 거리(mm). 화각(CAMERA_HFOV_DEG)과 IOD 가정에 비례해 틀리므로,
 * 자로 잰 거리와 다르면 화각 상수를 고친다
 */
export function eyeDistanceMm(frame: FaceFrame) {
  return (frame.imageSize.width / DEPTH_PER_Z) * mmPerPx(frame);
}

/** 눈과 같은 깊이의 점을 비친 자리에 그리는 변환 */
function eyeDepthTransform(frame: FaceFrame, screen: MirrorScreen, fit: MirrorFit): ViewTransform {
  const { width: w, height: h } = frame.imageSize;
  const a = frame.landmarks[RIGHT_IRIS_CENTER];
  const b = frame.landmarks[LEFT_IRIS_CENTER];
  const k = mmPerPx(frame);
  // 카메라 기준 실제 위치(mm). 사용자가 보는 방향으로 x 오른쪽, y 아래이고, 영상은 좌우가 반대라 x를 뒤집는다
  const ex = (w / 2 - (a.x + b.x) * (w / 2)) * k;
  const ey = ((a.y + b.y) * (h / 2) - h / 2) * k;
  // 반전 영상 좌표 u = w - x에서 P = ((u - w/2)k, (y - h/2)k). 화면 mm = scale·(E + P)/2 + d
  const half = (fit.scale * k) / 2;
  const x0 = (fit.scale * ex) / 2 - (half * w) / 2 + fit.dx;
  const y0 = (fit.scale * ey) / 2 - (half * h) / 2 + fit.dy;
  return {
    scale: half * screen.pxPerMm,
    offsetX: screen.originX + x0 * screen.pxPerMm,
    offsetY: screen.originY + y0 * screen.pxPerMm,
    mirrored: true,
  };
}

type Px = { x: number; y: number };

/** 보정 없이 계산한 두 눈 위치(predicted)를 사용자가 거울에서 맞춘 위치(seen)로 옮기는 보정 */
export function fitMirror(predicted: [Px, Px], seen: [Px, Px], screen: MirrorScreen): MirrorFit {
  const mm = (p: Px) => ({
    x: (p.x - screen.originX) / screen.pxPerMm,
    y: (p.y - screen.originY) / screen.pxPerMm,
  });
  const [p1, p2] = predicted.map(mm);
  const [s1, s2] = seen.map(mm);
  const scale =
    Math.hypot(s1.x - s2.x, s1.y - s2.y) / Math.max(1e-6, Math.hypot(p1.x - p2.x, p1.y - p2.y));
  return {
    scale,
    dx: (s1.x + s2.x) / 2 - (scale * (p1.x + p2.x)) / 2,
    dy: (s1.y + s2.y) / 2 - (scale * (p1.y + p2.y)) / 2,
  };
}

let cachedFit: MirrorFit | null = null;

/** 저장된 맞춤 보정. 없거나 읽지 못하면 보정 없음 */
export function loadMirrorFit(): MirrorFit {
  if (cachedFit) return cachedFit;
  try {
    const saved = JSON.parse(localStorage.getItem(FIT_KEY) ?? "null") as MirrorFit | null;
    cachedFit = saved && Number.isFinite(saved.scale) && saved.scale > 0 ? saved : NO_FIT;
  } catch {
    cachedFit = NO_FIT;
  }
  return cachedFit;
}

/** 맞춤 보정을 저장한다. null이면 지운다 */
export function saveMirrorFit(fit: MirrorFit | null) {
  cachedFit = fit ?? NO_FIT;
  try {
    if (fit) localStorage.setItem(FIT_KEY, JSON.stringify(fit));
    else localStorage.removeItem(FIT_KEY);
  } catch {
    // 저장에 실패해도 이번 실행에는 적용된다
  }
}
