// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FaceFrame, RegionName } from "@/features/face";

import { FRAME_GAP_MS } from "./baseline";
import type { CellLab } from "./cells";
import { clearRegisteredGaugeBaseline, saveRegisteredGaugeBaseline } from "./registered-baseline";
import { GRID } from "./spec";
import type { FrameState } from "./stability";
import { useGaugeBaseline, type GaugeBaselineStatus } from "./use-gauge-baseline";

const mocks = vi.hoisted(() => ({
  listener: null as ((frame: FaceFrame | null) => void) | null,
  regionVisible: true,
  match: vi.fn((...args: [unknown, unknown, AbortSignal?]) => {
    void args;
    return Promise.resolve({ exposure: "고정됨 (노출 500 · ISO 800)" });
  }),
  lock: vi.fn(() => Promise.resolve({ whiteBalance: "고정 안 함" })),
  unlock: vi.fn(() => Promise.resolve()),
  track: {},
  videoRef: { current: null as unknown },
}));
const video = () => ({
  videoWidth: 4,
  videoHeight: 4,
  srcObject: { getVideoTracks: () => [mocks.track] },
});
mocks.videoRef.current = video();

vi.mock("@/features/face", () => ({
  FRAME_STALE_MS: 300,
  isRegionInView: () => mocks.regionVisible,
  lockControls: mocks.lock,
  matchExposure: mocks.match,
  unlockControls: mocks.unlock,
  useCamera: () => ({ videoRef: mocks.videoRef }),
  useFaceFrame: (listener: (frame: FaceFrame | null) => void) => {
    mocks.listener = listener;
  },
}));
vi.mock("@/features/overlay", () => ({
  loadFaceMesh: () => Promise.resolve({ triangles: [], uv: [] }),
}));
vi.mock("./white", () => ({
  eyeSampler: () => ({ corners: new Int32Array(), weights: new Float32Array(), size: 0 }),
  readEyePixels: () => new Float32Array(),
  whiteOfFrames: (frames: Float32Array[]) => (frames.length === 15 ? [230, 220, 215] : null),
}));
vi.mock("./cells", () => ({
  cellSampler: () => ({ cell: new Int32Array(), samples: new Uint16Array() }),
  readCells: () => new Float32Array(GRID * GRID * 3).fill(50),
}));

let now = 0;
const frame = (
  pose: { yaw: number; pitch: number; roll: number } = {
    yaw: 0,
    pitch: 0,
    roll: 0,
  },
  trackingState: FaceFrame["trackingState"] = "tracking",
  usableRegions?: RegionName[],
): FaceFrame =>
  ({
    trackingState,
    usableRegions,
    timestamp: now,
    detectedAt: now,
    pose,
    eyes: { left: { openness: 1, blinking: false }, right: { openness: 1, blinking: false } },
    landmarks: Array.from({ length: 478 }, () => ({ x: 0.5, y: 0.5, z: 0 })),
    imageSize: { width: 640, height: 480 },
  }) as unknown as FaceFrame;

/** 정면 30장으로 정면을 정한 뒤, 기준 사진 n장을 간격을 두고 보낸다 */
async function feed(n: number) {
  await act(async () => {
    for (let i = 0; i < 30 + n; i++) {
      now += FRAME_GAP_MS;
      mocks.listener?.(frame());
    }
  });
}

type Result = {
  status: GaugeBaselineStatus;
  stepBaseline: (i: number) => unknown;
  takeNext: (next: number, makeup: string) => boolean;
  record: (at: number, state: FrameState, grid: CellLab | null) => void;
};
const probe: { current: Result | null } = { current: null };
type ProbeProps = {
  run: string;
  step: number;
  collecting: boolean;
  makeup?: string;
  regions?: RegionName[];
};
function Probe({ run, step, collecting, makeup, regions }: ProbeProps) {
  const result = useGaugeBaseline({ runId: run, step, collecting, makeup, regions });
  useEffect(() => {
    probe.current = result;
  });
  return null;
}
const latest = () => probe.current!;

let element: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.spyOn(performance, "now").mockImplementation(() => now);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    drawImage: () => {},
    getImageData: () => ({ width: 4, height: 4, data: new Uint8ClampedArray(64) }),
  } as unknown as CanvasRenderingContext2D);
  mocks.videoRef.current = video();
  mocks.regionVisible = true;
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
  mocks.lock.mockClear();
  mocks.match.mockClear();
  mocks.unlock.mockClear();
  clearRegisteredGaugeBaseline();
});

const render = (
  run: string,
  step: number,
  collecting: boolean,
  makeup = "foundation",
  regions?: RegionName[],
) =>
  act(async () =>
    root.render(
      <Probe run={run} step={step} collecting={collecting} makeup={makeup} regions={regions} />,
    ),
  );

describe("게이지 기준 모으기", () => {
  it("같은 카메라 세션의 얼굴 등록 기준을 첫 단계에서 다시 모으지 않고 쓴다", async () => {
    const baseline = {
      lab: new Float32Array(GRID * GRID * 3).fill(50),
      cells: new Uint8Array(GRID * GRID).fill(1),
      frames: 15,
    };
    saveRegisteredGaugeBaseline({
      runId: "registered",
      track: mocks.track as MediaStreamTrack,
      baseline,
      white: [230, 220, 215],
      center: 0.02,
      lock: { exposure: "얼굴 등록에서 고정됨" },
    });

    await render("registered", 0, true);

    expect(latest().stepBaseline(0)).toBe(baseline);
    expect(latest().status).toMatchObject({
      bare: baseline,
      white: [230, 220, 215],
      center: 0.02,
      lock: { exposure: "얼굴 등록에서 고정됨" },
    });
    expect(mocks.match).not.toHaveBeenCalled();
  });

  it("지금 단계 부위가 화면에 온전히 보여야 기준 사진을 모은다", async () => {
    mocks.regionVisible = false;
    await render("run", 0, true, "lip", ["lipsOuter"]);
    await feed(15);
    expect(latest().status.frames).toBe(0);
    expect(latest().status.front).toBe(false);

    mocks.regionVisible = true;
    await feed(15);
    expect(latest().stepBaseline(0)).not.toBeNull();
  });

  it("얼굴 전체 추적이 약해도 지금 단계 부위가 안정적으로 보이면 기준 사진을 모은다", async () => {
    await render("run", 0, true, "lip", ["lipsOuter"]);
    await act(async () => {
      for (let i = 0; i < 45; i++) {
        now += FRAME_GAP_MS;
        mocks.listener?.(frame(undefined, "degraded", ["lipsOuter"]));
      }
    });
    expect(latest().stepBaseline(0)).not.toBeNull();
  });

  it("준비 중 고개가 정면인지 화면에 알린다", async () => {
    await render("run", 0, true);
    await act(async () => {
      now += 600;
      mocks.listener?.(frame({ yaw: 0.4, pitch: 0, roll: 0 }));
    });
    expect(latest().status.front).toBe(false);

    await act(async () => {
      now += 600;
      mocks.listener?.(frame());
    });
    expect(latest().status.front).toBe(true);
  });

  it("첫 단계 준비 카드에서 카메라를 자동 밝기에 맞춰 잠근 뒤 15장을 모아 맨얼굴 기준으로 둔다", async () => {
    await render("run", 0, true);
    expect(mocks.match).toHaveBeenCalledTimes(1);
    expect(mocks.lock).toHaveBeenCalledWith(mocks.track, ["whiteBalance"]);
    expect(latest().status.lock).toEqual({
      exposure: "고정됨 (노출 500 · ISO 800)",
      whiteBalance: "고정 안 함",
    });
    await feed(15);
    expect(latest().status.bare?.frames).toBe(15);
    expect(latest().stepBaseline(0)).toBe(latest().status.bare);
    // 맨얼굴 기준과 같은 사진으로 흰자 색을 잰다
    expect(latest().status.white).toEqual([230, 220, 215]);
  });

  it("잠그는 동안에는 화면 밝기가 바뀌어 기준 사진을 모으지 않는다", async () => {
    let done: (v: { exposure: string }) => void = () => {};
    mocks.match.mockImplementationOnce(() => new Promise((resolve) => (done = resolve)));
    await render("run", 0, true);
    await feed(15);
    expect(latest().status.frames).toBe(0);
    await act(async () => done({ exposure: "고정됨" }));
    await feed(15);
    expect(latest().status.bare?.frames).toBe(15);
  });

  it("준비 카드를 일찍 닫아 기준을 못 만들었으면 같은 단계에서 다시 모은다", async () => {
    await render("run", 0, true);
    await feed(5);
    await render("run", 0, false);
    expect(latest().stepBaseline(0)).toBeNull();

    await render("run", 0, true);
    expect(latest().status.frames).toBe(0);
    await feed(15);
    expect(latest().stepBaseline(0)).not.toBeNull();
  });

  it("잠그는 동안 측정에서 받은 사진도 다음 단계 시작 기준에 남기지 않는다", async () => {
    mocks.match.mockImplementationOnce(() => new Promise(() => {}));
    await render("run", 0, true);
    await feed(0);
    const grid = new Float32Array(GRID * GRID * 3).fill(50);
    latest().record(now - 800, { faces: 1 }, grid);
    latest().record(now - 400, { faces: 1 }, grid);
    latest().record(now, { faces: 1 }, grid);

    expect(latest().takeNext(1, "lip")).toBe(false);
  });

  it("잠금이 실패하면 잠금 결과에 실패를 띄우고 자동 상태로 기준을 모은다", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    mocks.lock.mockImplementationOnce(() => Promise.reject(new Error("지원하지 않음")));
    await render("run", 0, true);
    expect(latest().status.lock).toEqual({ camera: "실패: 지원하지 않음" });
    await feed(15);
    expect(latest().status.bare?.frames).toBe(15);
  });

  it("카메라 트랙이 늦게 붙으면 기준 수집을 보류하고 프레임에서 잠금을 다시 시도한다", async () => {
    mocks.videoRef.current = {
      ...video(),
      srcObject: { getVideoTracks: () => [] },
    };
    await render("run", 0, true);
    await feed(15);
    expect(mocks.match).not.toHaveBeenCalled();
    expect(latest().status.frames).toBe(0);

    mocks.videoRef.current = video();
    await feed(1);
    expect(mocks.match).toHaveBeenCalledTimes(1);
    await feed(15);
    expect(latest().status.bare?.frames).toBe(15);
  });

  it("첫 준비 카드가 끝난 뒤 트랙이 붙어도 다음 단계에서 잠근 뒤 기준을 모은다", async () => {
    mocks.videoRef.current = {
      ...video(),
      srcObject: { getVideoTracks: () => [] },
    };
    await render("run", 0, true);
    await feed(15);
    await render("run", 0, false);
    expect(latest().status.bare).toBeNull();
    expect(mocks.match).not.toHaveBeenCalled();

    await render("run", 1, true);
    await feed(5);
    expect(latest().status.frames).toBe(0);

    mocks.videoRef.current = video();
    await feed(1);
    expect(mocks.match).toHaveBeenCalledTimes(1);
    await feed(15);
    expect(latest().stepBaseline(1)).not.toBeNull();
    expect(latest().status.bare).toBeNull();
  });

  it("첫 단계에서 다 모으지 못하면 맨얼굴 기준은 없고, 뒤 단계 기준을 맨얼굴 기준으로 쓰지 않는다", async () => {
    await render("run", 0, true);
    await feed(5);
    await render("run", 0, false);
    expect(latest().stepBaseline(0)).toBeNull();
    expect(latest().status.bare).toBeNull();
    // 카메라는 첫 모으기를 시작할 때 한 번만 잠근다
    expect(mocks.match).toHaveBeenCalledTimes(1);

    await render("run", 1, true);
    await feed(15);
    expect(latest().stepBaseline(1)).not.toBeNull();
    expect(latest().status.bare).toBeNull();
    expect(mocks.match).toHaveBeenCalledTimes(1);
  });

  it("맨얼굴 기준을 못 모으면 눈 화장 전 다음 준비 카드에서 다 모은 사진으로 흰자를 잰다", async () => {
    await render("run", 0, true);
    await feed(5);
    await render("run", 0, false);
    expect(latest().status.white).toBeNull();

    await render("run", 1, true, "blush");
    await feed(15);
    expect(latest().status.bare).toBeNull();
    expect(latest().status.white).toEqual([230, 220, 215]);
  });

  it("눈 화장 단계에 들어선 뒤에는 흰자를 재지 않는다", async () => {
    await render("run", 0, true);
    await feed(5);
    await render("run", 0, false);

    await render("run", 1, true, "eyeliner");
    await feed(15);
    expect(latest().stepBaseline(1)).not.toBeNull();
    expect(latest().status.white).toBeNull();

    await render("run", 2, true, "lip");
    await feed(15);
    expect(latest().stepBaseline(2)).not.toBeNull();
    expect(latest().status.white).toBeNull();
  });

  it("준비 카드가 떠 있지 않으면 모으지 않고, 다른 실행의 기준은 버린다", async () => {
    await render("run", 0, false);
    await feed(15);
    expect(latest().stepBaseline(0)).toBeNull();

    await render("run", 0, true);
    await feed(15);
    expect(latest().stepBaseline(0)).not.toBeNull();
    await render("other", 0, false);
    expect(latest().stepBaseline(0)).toBeNull();
    expect(latest().status.bare).toBeNull();
  });

  it("다른 실행을 시작하면 이전 잠금을 풀고 새 조명에 맞춰 다시 잠근다", async () => {
    await render("run", 0, true);
    await feed(15);

    await render("other", 0, true);

    expect(mocks.unlock).toHaveBeenCalledWith(mocks.track);
    expect(mocks.match).toHaveBeenCalledTimes(2);
    expect(mocks.lock).toHaveBeenCalledTimes(2);
  });

  it("잠그는 도중 실행이 바뀌면 이전 잠금을 취소한다", async () => {
    let signal: AbortSignal | undefined;
    mocks.match.mockImplementationOnce((_track, _video, current) => {
      signal = current;
      return new Promise(() => {});
    });
    await render("run", 0, true);

    await render("other", 0, true);

    expect(signal?.aborted).toBe(true);
    expect(mocks.unlock).toHaveBeenCalledWith(mocks.track);
    expect(mocks.match).toHaveBeenCalledTimes(2);
  });

  it("나갈 때 잠근 카메라를 푼다", async () => {
    await render("run", 0, true);
    await feed(15);
    await act(async () => root.unmount());
    root = createRoot(element);
    expect(mocks.unlock).toHaveBeenCalledWith(mocks.track);
  });
});
