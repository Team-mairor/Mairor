// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FaceFrame } from "@/features/face";

import type { Baseline } from "./baseline";
import { GRID } from "./spec";
import { WINDOW, type GaugeDisplay } from "./stability";
import { useGaugeMeasure, type GaugeMeasureInput } from "./use-gauge-measure";

const mocks = vi.hoisted(() => ({
  listener: null as ((frame: FaceFrame | null) => void) | null,
  faces: 1,
  ratio: 1 as number | null,
  videoRef: { current: { videoWidth: 4, videoHeight: 4 } as unknown },
}));

vi.mock("@/features/face", () => ({
  FRAME_STALE_MS: 300,
  useCamera: () => ({ videoRef: mocks.videoRef }),
  useFaceFrame: (listener: (frame: FaceFrame | null) => void) => {
    mocks.listener = listener;
  },
}));
vi.mock("@/features/overlay", () => ({
  loadFaceMesh: () => Promise.resolve({ triangles: [], uv: [] }),
}));
vi.mock("./use-gauge-baseline", () => ({
  loadCellSampler: () => Promise.resolve({ cells: {}, eyes: {} }),
  videoReader: () => () => ({ width: 4, height: 4, data: new Uint8ClampedArray(64) }),
}));
vi.mock("./area", () => ({
  areaCells: () => new Uint8Array(GRID * GRID),
  madeCells: () => new Uint8Array(GRID * GRID),
}));
vi.mock("./cells", () => ({ readCells: () => new Float32Array(GRID * GRID * 3) }));
vi.mock("./light", () => ({
  drift: () => ({ size: 0.5 }),
  lightChange: () => new Float32Array(GRID * GRID * 3),
}));
vi.mock("./frame", () => ({
  frameState: () => (mocks.faces ? { faces: 1, eyes: 0.35, faceWidth: 0.5 } : { faces: 0 }),
}));
vi.mock("./measure", () => ({
  gaugeBar: (ratio: number) => ratio * 50,
  framesMedian: (grids: Float32Array[]) => grids[0],
  linearOfSrgb: (v: number[]) => v,
  userSide: () => ({ side: {}, cells: 40 }),
  measure: () => ({
    ratio: mocks.ratio,
    bar: null,
    hue: null,
    chroma: null,
    hueSame: null,
    chromaSame: null,
    target: 5,
    sides: [],
    reason: mocks.ratio === null ? "tooFewCells" : null,
  }),
}));

let now = 0;
const frame = () =>
  ({
    trackingState: "tracking",
    timestamp: now,
    detectedAt: now,
    landmarks: [],
  }) as unknown as FaceFrame;

const start: Baseline = {
  lab: new Float32Array(GRID * GRID * 3),
  cells: new Uint8Array(GRID * GRID),
  frames: 15,
};
const base: GaugeMeasureInput = {
  active: true,
  key: "run:s1-1",
  makeup: "lip",
  gauge: null,
  guideSets: [],
  madeSets: [],
  start,
  white: [230, 220, 215],
};

const probe: { current: GaugeDisplay | null } = { current: null };
function Probe(input: GaugeMeasureInput) {
  const { display } = useGaugeMeasure(input);
  useEffect(() => {
    probe.current = display;
  });
  return null;
}

/** 측정 간격마다 사진을 n장 보낸다 */
async function feed(n: number) {
  await act(async () => {
    for (let i = 0; i < n; i++) {
      now += WINDOW.intervalMs;
      mocks.listener?.(frame());
    }
  });
}

let element: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.spyOn(performance, "now").mockImplementation(() => now);
  mocks.faces = 1;
  mocks.ratio = 1;
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
});

const render = (input: GaugeMeasureInput) => act(async () => root.render(<Probe {...input} />));

describe("게이지 재기", () => {
  it("레퍼런스만큼 바르면 위치선에 오고 비슷해요다", async () => {
    await render(base);
    await feed(3);
    expect(probe.current).toMatchObject({ bar: 50, label: "similar", reason: null });
  });

  it("단계 시작 기준이 없으면 측정값을 내지 않는다", async () => {
    await render({ ...base, start: null });
    await feed(3);
    expect(probe.current).toMatchObject({ bar: null, reason: "noBaseline" });
  });

  it("사진을 모두 거르면 마지막 값을 계속 유지한다", async () => {
    await render(base);
    await feed(3);
    mocks.faces = 0;
    // 최근 1초 창에 통과한 사진이 남아 있는 동안은 그대로 잰다
    await feed(4);
    expect(probe.current).toMatchObject({ bar: 50, stale: false });
    // 창이 비어도 마지막 값을 유지한다
    await feed(1);
    expect(probe.current).toMatchObject({ bar: 50, stale: true });
    await feed(10);
    expect(probe.current).toMatchObject({ bar: 50, stale: true, reason: "lost" });
  });

  it("재지 않는 동안에는 값을 내지 않는다", async () => {
    await render({ ...base, active: false });
    await feed(3);
    expect(probe.current).toBeNull();
  });

  it("이미 잰 뒤 멀어서 측정을 멈추면 마지막 위치를 유지한다", async () => {
    await render(base);
    await feed(3);
    expect(probe.current).toMatchObject({ bar: 50 });

    await render({ ...base, active: false });
    mocks.faces = 0;
    await feed(10);
    expect(probe.current).toMatchObject({ bar: 50 });
  });
});
