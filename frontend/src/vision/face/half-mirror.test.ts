import { describe, expect, it } from "vitest";

import {
  EyeHold,
  eyeDistanceMm,
  fitMirror,
  halfMirror,
  viewingEye,
  type MirrorScreen,
} from "./half-mirror";
import { LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER } from "./regions";
import type { FaceFrame, Point } from "./types";
import { toScreen } from "./view-transform";

const W = 1000;
const H = 1000;
/** 카메라가 요소 원점, 1px = 1mm라 결과가 곧 카메라 기준 화면 mm다 */
const SCREEN: MirrorScreen = { originX: 0, originY: 0, pxPerMm: 1 };
/** half-mirror.ts의 상수와 같은 값 */
const IOD_MM = 63;
const HFOV_DEG = 45;
const NOSE = 1;

/** 두 눈 가운데(eye)와 영상 px 눈 사이 거리(iod)로 만든 프레임. 1번 점은 따로 넣는다 */
function frameOf(eye: { x: number; y: number }, iod: number, nose: Point): FaceFrame {
  const landmarks: Point[] = Array.from({ length: 478 }, () => ({ x: eye.x, y: eye.y, z: 0 }));
  landmarks[RIGHT_IRIS_CENTER] = { x: eye.x - iod / 2 / W, y: eye.y, z: 0 };
  landmarks[LEFT_IRIS_CENTER] = { x: eye.x + iod / 2 / W, y: eye.y, z: 0 };
  landmarks[NOSE] = nose;
  return { landmarks, imageSize: { width: W, height: H } } as unknown as FaceFrame;
}

// 깊이를 그대로 믿을 때의 기하를 검증한다
const draw = (frame: FaceFrame, i: number, fit?: Parameters<typeof halfMirror>[2]) => {
  const r = halfMirror(frame, SCREEN, fit, 1, 0);
  return toScreen(r.frame.landmarks[i], frame.imageSize, r.view);
};

/** 카메라 기준 실제 위치(mm, 사용자가 보는 방향으로 x 오른쪽·y 아래, z 화면까지 거리) */
function world(p: Point, iod: number) {
  const k = IOD_MM / iod;
  const ze = (W / 2 / Math.tan((HFOV_DEG * Math.PI) / 360)) * k;
  const z = ze + (p.z ?? 0) * W * k;
  const r = z / ze;
  return { x: ((1 - p.x) * W - W / 2) * k * r, y: (p.y * H - H / 2) * k * r, z };
}

/** 눈 E에서 거울 뒤 허상 (P, -Zp)를 보는 시선이 화면(z = 0)을 지나는 점. 식을 거치지 않고 직선으로 구한다 */
function seenOnGlass(eye: Point, p: Point, iod: number) {
  const e = world(eye, iod);
  const q = world(p, iod);
  const t = e.z / (e.z + q.z);
  return { x: e.x + (q.x - e.x) * t, y: e.y + (q.y - e.y) * t };
}

describe("halfMirror", () => {
  it("눈과 같은 깊이의 점은 눈과 그 점의 가운데에 비친다", () => {
    const frame = frameOf({ x: 0.5, y: 0.5 }, 60, { x: 0.4, y: 0.6, z: 0 });
    // P = (100px, 100px) × 63/60 mm, E = 0 → 가운데는 52.5mm
    const p = draw(frame, NOSE);
    expect(p.x).toBeCloseTo(52.5, 6);
    expect(p.y).toBeCloseTo(52.5, 6);
  });

  it("깊이가 다른 점(코끝)도 시선과 화면이 만나는 자리에 그린다", () => {
    const eye = { x: 0.45, y: 0.62, z: 0 };
    const nose = { x: 0.47, y: 0.7, z: -0.06 };
    const frame = frameOf(eye, 80, nose);
    const want = seenOnGlass(eye, nose, 80);
    const got = draw(frame, NOSE);
    expect(got.x).toBeCloseTo(want.x, 6);
    expect(got.y).toBeCloseTo(want.y, 6);
  });

  it("깊이 기울기를 주면 눈보다 아래 점은 그만큼 먼 깊이의 자리에 그린다", () => {
    const eye = { x: 0.5, y: 0.5, z: 0 };
    const chin = { x: 0.5, y: 0.7, z: 0 };
    const frame = frameOf(eye, 80, chin);
    const tilted = halfMirror(frame, SCREEN, undefined, 1, 0.2);
    const got = toScreen(tilted.frame.landmarks[NOSE], frame.imageSize, tilted.view);
    // 세로 0.2 × 1000px 아래이므로 영상 폭 기준 깊이 0.2 × 0.2 = 0.04만큼 멀리 있는 점과 같다
    const want = seenOnGlass(eye, { ...chin, z: 0.04 }, 80);
    expect(got.x).toBeCloseTo(want.x, 6);
    expect(got.y).toBeCloseTo(want.y, 6);
    expect(got.y).toBeGreaterThan(draw(frame, NOSE).y);
  });

  it("비친 두 눈 사이는 거리와 상관없이 실제 IOD의 절반이다", () => {
    for (const iod of [40, 80, 160]) {
      const frame = frameOf({ x: 0.52, y: 0.6 }, iod, { x: 0.5, y: 0.5, z: 0 });
      const a = draw(frame, RIGHT_IRIS_CENTER);
      const b = draw(frame, LEFT_IRIS_CENTER);
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(IOD_MM / 2, 6);
    }
  });
});

describe("보는 눈", () => {
  /** 눈꺼풀 사이를 정한 프레임. 눈 폭 20px, 감은 눈은 2px·뜬 눈은 6px */
  const winking = (rightOpen: boolean, leftOpen: boolean) => {
    const frame = frameOf({ x: 0.5, y: 0.5 }, 60, { x: 0.5, y: 0.5, z: 0 });
    const lids = (up: number, down: number, a: number, b: number, cx: number, open: boolean) => {
      const gap = (open ? 6 : 2) / H;
      frame.landmarks[up] = { x: cx, y: 0.5 - gap / 2, z: 0 };
      frame.landmarks[down] = { x: cx, y: 0.5 + gap / 2, z: 0 };
      frame.landmarks[a] = { x: cx - 10 / W, y: 0.5, z: 0 };
      frame.landmarks[b] = { x: cx + 10 / W, y: 0.5, z: 0 };
    };
    lids(159, 145, 33, 133, 0.47, rightOpen);
    lids(386, 374, 362, 263, 0.53, leftOpen);
    return frame;
  };

  it("한쪽 눈을 감으면 뜬 눈, 아니면 맞출 때 쓴 눈으로 본다", () => {
    const fit = { scale: 1, dx: 0, dy: 0, eye: "right" as const };
    expect(viewingEye(winking(true, true), fit)).toBe("right");
    expect(viewingEye(winking(false, true), fit)).toBe("left");
    expect(viewingEye(winking(true, false), fit)).toBe("right");
    expect(viewingEye(winking(false, false), fit)).toBe("right");
    // 맞출 때 눈을 모르면 예전처럼 두 눈 가운데에서 본다
    expect(viewingEye(winking(false, true), { scale: 1, dx: 0, dy: 0 })).toBe(null);
  });

  it("한쪽 눈에서 본 점은 그 눈과 허상을 잇는 시선이 화면을 지나는 자리다", () => {
    const eye = { x: 0.46, y: 0.6, z: 0 };
    const nose = { x: 0.48, y: 0.68, z: -0.05 };
    const frame = frameOf(eye, 80, nose);
    for (const [side, iris] of [
      ["right", RIGHT_IRIS_CENTER],
      ["left", LEFT_IRIS_CENTER],
    ] as const) {
      const r = halfMirror(frame, SCREEN, undefined, 1, 0, side);
      const got = toScreen(r.frame.landmarks[NOSE], frame.imageSize, r.view);
      const want = seenOnGlass(frame.landmarks[iris], nose, 80);
      expect(got.x).toBeCloseTo(want.x, 6);
      expect(got.y).toBeCloseTo(want.y, 6);
    }
  });

  it("보는 눈을 바꾸면 비친 자리가 눈 사이의 절반만큼 옮겨진다", () => {
    const frame = frameOf({ x: 0.5, y: 0.5 }, 60, { x: 0.45, y: 0.55, z: 0 });
    const at = (side: "left" | "right") => {
      const r = halfMirror(frame, SCREEN, undefined, 1, 0, side);
      return toScreen(r.frame.landmarks[NOSE], frame.imageSize, r.view);
    };
    expect(Math.abs(at("right").x - at("left").x)).toBeCloseTo(IOD_MM / 2, 6);
  });
});

describe("EyeHold", () => {
  it("깜빡임처럼 짧게 한쪽만 감긴 것은 무시하고 0.4초 넘게 감아야 바꾼다", () => {
    const hold = new EyeHold();
    expect(hold.update("left", 0)).toBe(null);
    expect(hold.update(null, 200)).toBe(null);
    expect(hold.update("left", 300)).toBe(null);
    expect(hold.update("left", 650)).toBe(null);
    expect(hold.update("left", 700)).toBe("left");
  });
  it("두 눈을 다시 뜨면 잠시 뒤 맞출 때 쓴 눈으로 돌아간다", () => {
    const hold = new EyeHold();
    hold.update("left", 0);
    hold.update("left", 500);
    expect(hold.update(null, 600)).toBe("left");
    expect(hold.update(null, 760)).toBe(null);
  });
});

describe("eyeDistanceMm", () => {
  it("눈 사이 영상 px로 잰 눈 깊이를 돌려준다", () => {
    const eye = { x: 0.5, y: 0.5, z: 0 };
    const frame = frameOf(eye, 90, eye);
    expect(eyeDistanceMm(frame)).toBeCloseTo(world(eye, 90).z, 6);
  });
});

describe("fitMirror", () => {
  it("맞춘 배율로 그리면 두 눈 가운데가 사용자가 맞춘 자리에 오고 간격만 그만큼 바뀐다", () => {
    const frame = frameOf({ x: 0.48, y: 0.64 }, 70, { x: 0.5, y: 0.7, z: -0.05 });
    const mid = (fit?: Parameters<typeof draw>[2]) => {
      const a = draw(frame, RIGHT_IRIS_CENTER, fit);
      const b = draw(frame, LEFT_IRIS_CENTER, fit);
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, gap: Math.hypot(a.x - b.x, a.y - b.y) };
    };
    const before = mid();
    const seen = { x: before.x + 12, y: before.y - 7 };
    const fit = fitMirror(before, seen, SCREEN, 1.08);
    const after = mid(fit);
    expect(after.x).toBeCloseTo(seen.x, 6);
    expect(after.y).toBeCloseTo(seen.y, 6);
    expect(after.gap).toBeCloseTo(before.gap * 1.08, 6);
  });
});
