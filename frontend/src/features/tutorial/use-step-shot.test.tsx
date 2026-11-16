// @vitest-environment jsdom
import { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { FaceFrame, RegionName } from "@/features/face";

import { SHOT_FALLBACK_MS, STILL_MAX_WAIT_MS, STILL_MS, useStepShot } from "./use-step-shot";
import frontJson from "../../../public/fixtures/faces/front.json";

const face = vi.hoisted(() => ({
  listener: null as ((frame: FaceFrame | null) => void) | null,
  snap: vi.fn<() => string | null>(),
}));
vi.mock("@/features/face", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/face")>()),
  useCamera: () => ({ videoRef: { current: null } }),
  useFaceFrame: (listener: (frame: FaceFrame | null) => void) => {
    face.listener = listener;
  },
  snapMirrored: face.snap,
}));

const front = frontJson as unknown as FaceFrame;
/** 지금 검출한 프레임. lipsOut이면 입술이 화면 밖에 있다 */
const frame = (extra: Partial<FaceFrame> = {}, lipsOut = false): FaceFrame => {
  const now = performance.now();
  const regionVisibility = lipsOut
    ? {
        ...front.regionVisibility,
        lipsOuter: { ...front.regionVisibility.lipsOuter, inFrameRatio: 0 },
      }
    : front.regionVisibility;
  return {
    ...front,
    timestamp: now,
    detectedAt: now,
    trackingState: "tracking",
    regionVisibility,
    ...extra,
  };
};

let shot: ReturnType<typeof useStepShot>;
const onShot = vi.fn();
let probeRegions: RegionName[] = ["lipsOuter"];
let probeWhole = false;
function Probe() {
  const value = useStepShot(probeRegions, onShot, probeWhole);
  useLayoutEffect(() => {
    shot = value;
  });
  return null;
}

let root: Root;
const feed = async (f: FaceFrame | null, ms = 0) => {
  await act(async () => {
    if (ms) vi.advanceTimersByTime(ms);
    face.listener!(f);
  });
};

beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.useFakeTimers();
  vi.clearAllMocks();
  face.snap.mockReturnValue("data:image/jpeg;base64,x");
  root = createRoot(document.createElement("div"));
  await act(async () => root.render(<Probe />));
});
afterEach(async () => {
  probeWhole = false;
  await act(async () => root.unmount());
  vi.useRealTimers();
});

describe("useStepShot", () => {
  it("얼굴이 잠깐 멈추면 부위 확대 칸과 함께 찍는다", async () => {
    await feed(frame());
    await act(async () => shot.start());
    expect(shot.state).toBe("waiting");
    await feed(frame(), 10);
    await feed(frame(), STILL_MS);
    expect(onShot).toHaveBeenCalledTimes(1);
    expect(onShot.mock.calls[0][0]).toMatchObject({ url: "data:image/jpeg;base64,x" });
    expect(onShot.mock.calls[0][0].box).not.toBeNull();
    expect(shot.state).toBe("idle");
  });

  it("마지막 사진은 부위가 보여도 턱까지 얼굴 전체가 들어와야 찍는다", async () => {
    probeWhole = true;
    await act(async () => root.render(<Probe />));
    const chinCut = frame({
      regionVisibility: {
        ...front.regionVisibility,
        faceOval: { ...front.regionVisibility.faceOval, inFrameRatio: 0.7 },
      },
    });
    await act(async () => shot.start());
    for (let t = 0; t < STILL_MAX_WAIT_MS * 2; t += 200) await feed(chinCut, 200);
    expect(onShot).not.toHaveBeenCalled();
    expect(shot.state).toBe("outOfView");
    for (let t = 0; t <= STILL_MS + 200; t += 100) await feed(frame(), 100);
    expect(onShot).toHaveBeenCalledTimes(1);
  });

  it("찍을 부위가 화면 밖이면 찍지 않고 기다리며, 촬영 취소로 대기를 접는다", async () => {
    await act(async () => shot.start());
    for (let t = 0; t < STILL_MAX_WAIT_MS * 2; t += 200) await feed(frame({}, true), 200);
    expect(onShot).not.toHaveBeenCalled();
    expect(shot.state).toBe("outOfView");
    await act(async () => shot.cancel());
    expect(shot.state).toBe("idle");
    await feed(frame(), SHOT_FALLBACK_MS);
    expect(onShot).not.toHaveBeenCalled();
  });

  it("추적이 끊기면 대비 시간 뒤 실패로 두고 다시 찍을 수 있다", async () => {
    await act(async () => shot.start());
    await feed(frame({ trackingState: "lost" }));
    await act(async () => vi.advanceTimersByTime(SHOT_FALLBACK_MS));
    expect(shot.state).toBe("failed");
    expect(onShot).not.toHaveBeenCalled();
  });

  it("검출 시각이 오래된 프레임으로는 찍지 않는다", async () => {
    await feed(frame());
    await act(async () => shot.start());
    // 렌더는 계속 오지만 실제 검출은 1초 전에 멈췄다
    const old = performance.now();
    await act(async () => vi.advanceTimersByTime(1000));
    await feed(frame({ detectedAt: old, timestamp: old }));
    await act(async () => vi.advanceTimersByTime(SHOT_FALLBACK_MS));
    expect(shot.state).toBe("failed");
    expect(onShot).not.toHaveBeenCalled();
  });

  it("찍을 부위를 모르면 찍지 않고 실패로 둔다", async () => {
    probeRegions = [];
    await act(async () => root.render(<Probe />));
    await act(async () => shot.start());
    await feed(frame(), STILL_MAX_WAIT_MS);
    expect(onShot).not.toHaveBeenCalled();
    expect(shot.state).toBe("failed");
    probeRegions = ["lipsOuter"];
  });

  it("카메라 영상을 못 찍으면 실패로 둔다", async () => {
    face.snap.mockReturnValue(null);
    await act(async () => shot.start());
    await act(async () => vi.advanceTimersByTime(SHOT_FALLBACK_MS));
    expect(shot.state).toBe("failed");
    expect(shot.error).toBeNull();
  });

  it("저장이 실패하면 실패로 두고 이유를 남기며, 다시 찍기를 시작하면 이유를 지운다", async () => {
    const reason = new Error("업로드 실패");
    onShot.mockRejectedValueOnce(reason);
    await feed(frame());
    await act(async () => shot.start());
    await feed(frame(), 10);
    await feed(frame(), STILL_MS);
    expect(onShot).toHaveBeenCalledTimes(1);
    expect(shot.state).toBe("failed");
    expect(shot.error).toBe(reason);

    await act(async () => shot.start());
    expect(shot.state).toBe("waiting");
    expect(shot.error).toBeNull();
  });
});
