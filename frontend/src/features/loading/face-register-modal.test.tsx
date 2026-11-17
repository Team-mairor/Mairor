// @vitest-environment jsdom
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FaceRegisterModal } from "./face-register-modal";

const mocks = vi.hoisted(() => ({
  track: { id: "camera" },
  camera: {
    status: "ready",
    start: vi.fn(),
    videoRef: { current: { srcObject: { getVideoTracks: () => [] as object[] } } },
  },
  frame: { current: null as object | null },
  passedNow: () => true,
  capture: vi.fn(),
  save: vi.fn(),
  pixels: vi.fn(),
  saveBrows: vi.fn(),
  saveGauge: vi.fn(),
  gaugePush: true,
  loadSampler: vi.fn(),
}));
vi.mock("@/vision/face", () => ({
  CHECKS: ["light", "distance", "front", "clear"],
  DISTANCE_HINT_TEXT: {},
  allPassed: (check: Record<string, boolean>) => Object.values(check).every(Boolean),
  captureFace: mocks.capture,
  eyesClosed: () => false,
  hasMirrorFit: () => true,
  loadMirrorFit: () => null,
  lockControls: async () => ({ whiteBalance: "고정됨" }),
  matchExposure: async () => ({ exposure: "고정됨" }),
  saveFacePhoto: mocks.save,
  useCamera: () => mocks.camera,
  useFaceCheck: (active: boolean) => ({
    check: { light: active, distance: active, front: active, clear: active },
    found: active,
    hint: null,
    frame: mocks.frame,
    passedNow: mocks.passedNow,
  }),
}));
vi.mock("@/features/gauge", () => ({
  loadCellSampler: mocks.loadSampler,
  videoReader: () => () => ({ width: 1, height: 1, data: new Uint8ClampedArray(4) }),
}));
vi.mock("@/domain/gauge", () => ({
  saveRegisteredGaugeBaseline: mocks.saveGauge,
  RegisteredBaselineCollector: class {
    count = 0;
    get done() {
      return this.count >= 15;
    }
    push() {
      if (!mocks.gaugePush) return false;
      this.count = 15;
      return true;
    }
    reset() {
      this.count = 0;
    }
    build() {
      return this.done
        ? {
            baseline: { lab: new Float32Array(), cells: new Uint8Array(), frames: 15 },
            white: null,
            center: 0,
          }
        : null;
    }
  },
}));
vi.mock("@/vision/guide", () => ({
  readPixels: mocks.pixels,
  saveBrowsFrom: mocks.saveBrows,
}));
vi.mock("@/features/live", () => ({
  FaceStateProvider: ({ children }: { children: ReactNode }) => children,
  useCameraErrorNote: () => null,
}));
vi.mock("@/features/mirror-fit", () => ({ MirrorFitView: () => null }));
vi.mock("./face-demo", () => ({ FaceDemo: () => null }));
vi.mock("./face-position", () => ({ FacePosition: () => null }));

let element: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "performance"] });
  vi.clearAllMocks();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  mocks.capture.mockResolvedValue(new Blob(["face"]));
  mocks.gaugePush = true;
  mocks.loadSampler.mockResolvedValue({ cells: {}, eyes: {} });
  mocks.frame.current = { pose: { yaw: 0, pitch: 0, roll: 0 } };
  mocks.camera.videoRef.current.srcObject.getVideoTracks = () => [mocks.track];
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  mocks.frame.current = null;
  await act(async () => root.unmount());
  element.remove();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function register(pouchReviewed = false, onDone = vi.fn()) {
  await act(async () =>
    root.render(
      <FaceRegisterModal
        runId="run"
        pct={20}
        barText="분석 중"
        replay={false}
        pouchReviewed={pouchReviewed}
        onDone={onDone}
        onLater={vi.fn()}
      />,
    ),
  );
  const start = Array.from(document.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("얼굴 등록 시작"),
  )!;
  await act(async () => start.click());
  await act(async () => Promise.resolve());
  await act(async () => vi.advanceTimersByTime(1550));
}

describe("얼굴 등록 완료 안내", () => {
  it.each([
    [false, "등록 완료 · 파우치 확인"],
    [true, "등록 완료"],
  ] as const)("파우치 확인 여부 %s에 맞는 다음 동작을 안내한다", async (pouchReviewed, label) => {
    const onDone = vi.fn();
    await register(pouchReviewed, onDone);
    expect(mocks.capture).toHaveBeenCalledOnce();
    expect(mocks.save).toHaveBeenCalledWith("run", expect.any(Blob));
    const done = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent === label,
    );
    expect(done).toBeTruthy();
    expect(done!.disabled).toBe(false);
    await act(async () => done!.click());
    expect(onDone).toHaveBeenCalledOnce();
  });
});

describe("게이지 기준 수집 안내", () => {
  it("등록 조건을 통과해도 기준 사진이 모이지 않으면 카메라를 보라고 안내한다", async () => {
    mocks.gaugePush = false;
    await register();
    expect(document.body.textContent).toContain("카메라를 정면으로 봐 주세요");
    expect(mocks.capture).not.toHaveBeenCalled();
  });

  it("카메라 기준 준비에 실패하면 다시 준비해서 등록한다", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    mocks.loadSampler.mockRejectedValueOnce(new Error("load failed"));
    await register();
    expect(document.body.textContent).toContain("카메라 기준을 준비하지 못했어요");
    const retry = Array.from(document.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("카메라 기준 다시 준비"),
    )!;
    await act(async () => retry.click());
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTime(1550));
    expect(mocks.capture).toHaveBeenCalledOnce();
  });
});

describe("등록 사진의 원래 눈썹", () => {
  it("찍은 순간의 얼굴과 픽셀로 눈썹을 찾아 그 사진에 붙인다", async () => {
    const frame = { landmarks: [] };
    const pixels = { width: 1, height: 1, data: new Uint8ClampedArray(4) };
    mocks.frame.current = frame;
    mocks.pixels.mockReturnValue(pixels);
    await register();
    const photo = mocks.save.mock.calls[0][1];
    expect(mocks.saveBrows).toHaveBeenCalledWith("run", photo, pixels, frame);
  });

  it("얼굴 프레임이 없으면 눈썹을 찾지 않는다", async () => {
    mocks.frame.current = null;
    await register();
    expect(mocks.save).not.toHaveBeenCalled();
    expect(mocks.saveBrows).not.toHaveBeenCalled();
  });
});
