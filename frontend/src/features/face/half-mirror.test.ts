import { describe, expect, it } from "vitest";

import { eyeDistanceMm, fitMirror, halfMirror, type MirrorScreen } from "./half-mirror";
import { LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER } from "./regions";
import type { FaceFrame, Point } from "./types";
import { toScreen } from "./view-transform";

const W = 1000;
const H = 1000;
/** 카메라가 요소 원점, 1px = 1mm라 결과가 곧 카메라 기준 화면 mm다 */
const SCREEN: MirrorScreen = { originX: 0, originY: 0, pxPerMm: 1 };
/** half-mirror.ts의 상수와 같은 값 */
const IOD_MM = 63;
const HFOV_DEG = 66;
const NOSE = 1;

/** 두 눈 가운데(eye)와 영상 px 눈 사이 거리(iod)로 만든 프레임. 1번 점은 따로 넣는다 */
function frameOf(eye: { x: number; y: number }, iod: number, nose: Point): FaceFrame {
  const landmarks: Point[] = Array.from({ length: 478 }, () => ({ x: eye.x, y: eye.y, z: 0 }));
  landmarks[RIGHT_IRIS_CENTER] = { x: eye.x - iod / 2 / W, y: eye.y, z: 0 };
  landmarks[LEFT_IRIS_CENTER] = { x: eye.x + iod / 2 / W, y: eye.y, z: 0 };
  landmarks[NOSE] = nose;
  return { landmarks, imageSize: { width: W, height: H } } as unknown as FaceFrame;
}

const draw = (frame: FaceFrame, i: number, fit?: Parameters<typeof halfMirror>[2]) => {
  const r = halfMirror(frame, SCREEN, fit);
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

  it("비친 두 눈 사이는 거리와 상관없이 실제 IOD의 절반이다", () => {
    for (const iod of [40, 80, 160]) {
      const frame = frameOf({ x: 0.52, y: 0.6 }, iod, { x: 0.5, y: 0.5, z: 0 });
      const a = draw(frame, RIGHT_IRIS_CENTER);
      const b = draw(frame, LEFT_IRIS_CENTER);
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeCloseTo(IOD_MM / 2, 6);
    }
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
  it("맞춘 보정을 쓰면 두 눈이 사용자가 맞춘 자리에 그려진다", () => {
    const frame = frameOf({ x: 0.48, y: 0.64 }, 70, { x: 0.5, y: 0.7, z: -0.05 });
    const predicted = [draw(frame, RIGHT_IRIS_CENTER), draw(frame, LEFT_IRIS_CENTER)] as const;
    const seen = [
      { x: predicted[0].x * 1.08 + 12, y: predicted[0].y * 1.08 - 7 },
      { x: predicted[1].x * 1.08 + 12, y: predicted[1].y * 1.08 - 7 },
    ] as const;
    const fit = fitMirror([...predicted], [...seen], SCREEN);
    const a = draw(frame, RIGHT_IRIS_CENTER, fit);
    const b = draw(frame, LEFT_IRIS_CENTER, fit);
    expect(a.x).toBeCloseTo(seen[0].x, 6);
    expect(a.y).toBeCloseTo(seen[0].y, 6);
    expect(b.x).toBeCloseTo(seen[1].x, 6);
    expect(b.y).toBeCloseTo(seen[1].y, 6);
  });
});
