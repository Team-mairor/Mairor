import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createFaceInference, FrameCaptureError, type InferenceResult } from "./inference";
import { REGIONS } from "./regions";
import { FaceTracker } from "./tracker";
import type { FaceFrame } from "./types";
import data from "../../../public/fixtures/faces/front.json";

vi.mock("./inference", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./inference")>()),
  createFaceInference: vi.fn(),
}));

const empty: InferenceResult = {
  result: { faceLandmarks: [], faceBlendshapes: [], facialTransformationMatrixes: [] },
  detectMs: 1,
  largestMs: 0,
};
let callbacks: Map<number, () => Promise<void>>;
let id: number;
let video: HTMLVideoElement;
let resolveFrame: (value: InferenceResult) => void;
let detect: ReturnType<typeof vi.fn>;
let tracker: FaceTracker;

beforeEach(() => {
  callbacks = new Map();
  id = 0;
  vi.stubGlobal("HTMLMediaElement", { HAVE_CURRENT_DATA: 2 });
  vi.stubGlobal("document", {
    visibilityState: "visible",
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  });
  video = {
    readyState: 2,
    videoWidth: 640,
    videoHeight: 480,
    currentTime: 1,
    requestVideoFrameCallback: (callback: () => Promise<void>) => {
      callbacks.set(++id, callback);
      return id;
    },
    cancelVideoFrameCallback: (key: number) => callbacks.delete(key),
  } as unknown as HTMLVideoElement;
  detect = vi.fn(
    () =>
      new Promise<InferenceResult>((resolve) => {
        resolveFrame = resolve;
      }),
  );
  vi.mocked(createFaceInference).mockResolvedValue({ backend: "worker", detect, dispose: vi.fn() });
});
afterEach(() => {
  tracker?.dispose();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

function nextFrame() {
  const [key, callback] = callbacks.entries().next().value!;
  callbacks.delete(key);
  return callback();
}

describe("비동기 추적 중 카메라 수명", () => {
  it("한 눈만 보이는 연속 관측은 부분 추적에 쓰고 얼굴 전체 판정은 유지한다", async () => {
    const listener = vi.fn();
    const eye = REGIONS.rightEye.indices.map((i) => data.landmarks[i]);
    const rect = {
      x0: Math.min(...eye.map((p) => p.x)) - 0.001,
      x1: Math.max(...eye.map((p) => p.x)) + 0.001,
      y0: Math.min(...eye.map((p) => p.y)) - 0.001,
      y1: Math.max(...eye.map((p) => p.y)) + 0.001,
    };
    tracker = new FaceTracker(video, listener, {
      closeUp: "off",
      smoothing: null,
      visibleRect: rect,
    });
    await tracker.start();
    const observed = {
      ...empty,
      result: {
        ...empty.result,
        faceLandmarks: [data.landmarks.map((p) => ({ ...p, z: 0, visibility: 1 }))],
      },
    };
    for (let i = 0; i < 2; i++) {
      Object.assign(video, { currentTime: i + 2 });
      const pending = nextFrame();
      resolveFrame(observed);
      await pending;
    }
    const frame = listener.mock.calls[1][0] as FaceFrame;
    expect(frame.trackingState).toBe("degraded");
    expect(frame.usableRegions).toContain("rightEye");
    expect(frame.regionVisibility.leftEye.inFrameRatio).toBe(0);
    expect(frame.detectedAt).toBe(frame.timestamp);
  });
  it("일시 정지 뒤 도착한 결과를 버리고 재개 시 새 영상부터 추적한다", async () => {
    const listener = vi.fn();
    tracker = new FaceTracker(video, listener);
    await tracker.start();
    const pending = nextFrame();
    tracker.stop();
    tracker.reset();
    await tracker.start();
    resolveFrame(empty);
    await pending;
    expect(listener).not.toHaveBeenCalled();
    expect(callbacks.size).toBe(1);
    const next = nextFrame();
    resolveFrame(empty);
    await next;
    expect(listener).toHaveBeenCalledOnce();
  });

  it("추론 중 해상도가 바뀌면 이전 좌표를 버리고 루프를 유지한다", async () => {
    const listener = vi.fn();
    tracker = new FaceTracker(video, listener);
    await tracker.start();
    const pending = nextFrame();
    Object.assign(video, { videoWidth: 1280 });
    resolveFrame(empty);
    await pending;
    expect(listener).not.toHaveBeenCalled();
    expect(callbacks.size).toBe(1);
    const next = nextFrame();
    resolveFrame(empty);
    await next;
    expect(listener).toHaveBeenCalledOnce();
  });

  it("같은 영상 프레임은 다시 추론하지 않는다", async () => {
    tracker = new FaceTracker(video, vi.fn());
    await tracker.start();
    const pending = nextFrame();
    resolveFrame(empty);
    await pending;
    await nextFrame();
    expect(detect).toHaveBeenCalledOnce();
    expect(callbacks.size).toBe(1);
  });

  it("추적 중 Worker가 실패하면 메인 스레드 추론으로 이어 간다", async () => {
    const onError = vi.fn();
    const workerDispose = vi.fn();
    const mainDetect = vi.fn(async () => empty);
    vi.mocked(createFaceInference)
      .mockResolvedValueOnce({
        backend: "worker",
        detect: vi.fn(async () => {
          throw new Error("얼굴 추론 응답 시간 초과");
        }),
        dispose: workerDispose,
      })
      .mockResolvedValueOnce({ backend: "main", detect: mainDetect, dispose: vi.fn() });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const listener = vi.fn();
    tracker = new FaceTracker(video, listener, {}, onError);
    await tracker.start();
    await nextFrame();
    await vi.waitFor(() => expect(callbacks.size).toBe(1));
    expect(workerDispose).toHaveBeenCalledOnce();
    expect(createFaceInference).toHaveBeenLastCalledWith({ worker: false });
    expect(tracker.stats.backend).toBe("main");
    Object.assign(video, { currentTime: 2 });
    await nextFrame();
    expect(mainDetect).toHaveBeenCalledOnce();
    expect(listener).toHaveBeenCalledOnce();
    expect(onError).not.toHaveBeenCalled();
  });

  it("추론 밖에서 난 예외는 Worker 실패로 보지 않고 멈춘 뒤 알린다", async () => {
    const onError = vi.fn();
    const dispose = vi.fn();
    vi.mocked(createFaceInference).mockResolvedValue({ backend: "worker", detect, dispose });
    // 근접 모드의 입력 캔버스를 만들 수 없는 환경이라 입력 준비에서 예외가 난다
    tracker = new FaceTracker(video, vi.fn(), { closeUp: "on" }, onError);
    await tracker.start();
    await nextFrame();
    expect(onError).toHaveBeenCalledOnce();
    expect(detect).not.toHaveBeenCalled();
    expect(dispose).not.toHaveBeenCalled();
    expect(createFaceInference).toHaveBeenCalledOnce();
  });

  it("영상 이미지를 만들지 못한 프레임은 Worker를 유지한 채 건너뛰고 계속 실패하면 알린다", async () => {
    const onError = vi.fn();
    const dispose = vi.fn();
    const failing = vi.fn(async () => {
      throw new FrameCaptureError(new Error("InvalidStateError"));
    });
    vi.mocked(createFaceInference).mockResolvedValue({
      backend: "worker",
      detect: failing,
      dispose,
    });
    tracker = new FaceTracker(video, vi.fn(), { closeUp: "off" }, onError);
    await tracker.start();
    for (let i = 0; i < 29; i++) {
      Object.assign(video, { currentTime: i + 2 });
      await nextFrame();
    }
    expect(onError).not.toHaveBeenCalled();
    expect(dispose).not.toHaveBeenCalled();
    expect(createFaceInference).toHaveBeenCalledOnce();
    expect(callbacks.size).toBe(1);
    Object.assign(video, { currentTime: 100 });
    await nextFrame();
    expect(onError).toHaveBeenCalledOnce();
    expect(createFaceInference).toHaveBeenCalledOnce();
  });

  it("추론 응답을 기다리는 동안은 영상 멈춤으로 보지 않는다", async () => {
    vi.useFakeTimers();
    try {
      const onError = vi.fn();
      tracker = new FaceTracker(video, vi.fn(), {}, onError);
      await tracker.start();
      void nextFrame();
      await vi.advanceTimersByTimeAsync(9000);
      expect(onError).not.toHaveBeenCalled();
      resolveFrame(empty);
      await vi.advanceTimersByTimeAsync(0);
      expect(callbacks.size).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("메인 스레드 추론도 실패하면 멈추고 알린다", async () => {
    const onError = vi.fn();
    const error = new Error("GPU 컨텍스트 손실");
    vi.mocked(createFaceInference).mockResolvedValue({
      backend: "main",
      detect: vi.fn(async () => {
        throw error;
      }),
      dispose: vi.fn(),
    });
    tracker = new FaceTracker(video, vi.fn(), {}, onError);
    await tracker.start();
    await nextFrame();
    expect(onError).toHaveBeenCalledWith(error);
    expect(createFaceInference).toHaveBeenCalledOnce();
    expect(callbacks.size).toBe(0);
  });

  it("모델 로딩 중 중지했다가 다시 시작하거나 초기화해도 루프를 하나만 시작한다", async () => {
    for (const interrupt of ["restart", "reset"] as const) {
      callbacks.clear();
      let resolveInit: (value: Awaited<ReturnType<typeof createFaceInference>>) => void = () => {};
      vi.mocked(createFaceInference).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveInit = resolve;
          }),
      );
      tracker?.dispose();
      tracker = new FaceTracker(video, vi.fn());
      const starting = tracker.start();
      if (interrupt === "restart") {
        tracker.stop();
        void tracker.start();
      } else tracker.reset();
      resolveInit({ backend: "worker", detect, dispose: vi.fn() });
      await starting;
      expect(callbacks.size).toBe(1);
    }
  });

  it("메인 스레드로 바꾸는 동안 초기화돼도 추적을 이어 간다", async () => {
    let resolveMain: (value: Awaited<ReturnType<typeof createFaceInference>>) => void = () => {};
    vi.mocked(createFaceInference)
      .mockResolvedValueOnce({
        backend: "worker",
        detect: vi.fn(async () => {
          throw new Error("얼굴 추론 응답 시간 초과");
        }),
        dispose: vi.fn(),
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveMain = resolve;
          }),
      );
    vi.spyOn(console, "warn").mockImplementation(() => {});
    tracker = new FaceTracker(video, vi.fn());
    await tracker.start();
    await nextFrame();
    tracker.reset();
    resolveMain({ backend: "main", detect: vi.fn(async () => empty), dispose: vi.fn() });
    await vi.waitFor(() => expect(callbacks.size).toBe(1));
    expect(tracker.stats.backend).toBe("main");
  });

  it("모델 로딩 중 중지해도 뒤늦게 루프가 시작되지 않는다", async () => {
    let resolveInit: (value: Awaited<ReturnType<typeof createFaceInference>>) => void = () => {};
    vi.mocked(createFaceInference).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveInit = resolve;
        }),
    );
    tracker = new FaceTracker(video, vi.fn());
    const starting = tracker.start();
    tracker.stop();
    resolveInit({ backend: "worker", detect, dispose: vi.fn() });
    await starting;
    expect(callbacks.size).toBe(0);
  });
});
