import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createFaceInference } from "./inference";
import { createFaceLandmarker } from "./landmarker";

vi.mock("./landmarker", () => ({
  landmarkerInfo: {},
  landmarkerPreference: () => ({ delegate: "auto" }),
  createFaceLandmarker: vi.fn(async () => ({
    detectForVideo: () => ({ faceLandmarks: [] }),
    close: vi.fn(),
  })),
  createFaceDetector: vi.fn(async () => null),
}));

class TestWorker {
  static current: TestWorker;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onerror: ((event: { message: string }) => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() {
    TestWorker.current = this;
  }
  emit(data: unknown) {
    this.onmessage?.({ data });
  }
}

const result = { type: "result", id: 1, result: { faceLandmarks: [] }, detectMs: 10, largestMs: 0 };
const input = {} as HTMLCanvasElement;
async function start() {
  const ready = createFaceInference();
  TestWorker.current.emit({ type: "ready", delegate: "GPU" });
  return ready;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("Worker", TestWorker);
  vi.stubGlobal("OffscreenCanvas", class {});
  vi.stubGlobal(
    "createImageBitmap",
    vi.fn(async () => ({ close: vi.fn() })),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("얼굴 추론 Worker 수명", () => {
  it("영상 캡처 중과 추론 중에는 요청을 쌓지 않고 일치하는 응답만 받는다", async () => {
    const engine = await start();
    const pending = engine.detect(input, 1, false);
    await expect(engine.detect(input, 2, false)).rejects.toThrow("하나만");
    await Promise.resolve();
    TestWorker.current.emit({ ...result, id: 99 });
    await expect(engine.detect(input, 3, false)).rejects.toThrow("하나만");
    TestWorker.current.emit(result);
    await expect(pending).resolves.toMatchObject({ detectMs: 10 });
    engine.dispose();
    expect(TestWorker.current.terminate).toHaveBeenCalledOnce();
  });

  it("종료하면 진행 중 추론을 취소하고 늦은 응답을 사용하지 않는다", async () => {
    const engine = await start();
    const pending = engine.detect(input, 1, false);
    await Promise.resolve();
    const rejected = expect(pending).rejects.toThrow("종료");
    engine.dispose();
    await rejected;
    TestWorker.current.emit(result);
    await expect(engine.detect(input, 2, false)).rejects.toThrow("종료");
  });

  it("Worker 준비 실패는 기존 추론으로 복귀한다", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const pending = createFaceInference();
    TestWorker.current.emit({ type: "error", message: "no GPU context" });
    const engine = await pending;
    expect(engine.backend).toBe("main");
    expect(createFaceLandmarker).toHaveBeenCalledOnce();
    engine.dispose();
    warn.mockRestore();
  });

  it("응답이 끊기면 Worker를 종료해 무한 대기를 막는다", async () => {
    const engine = await start();
    const pending = engine.detect(input, 1, false);
    await Promise.resolve();
    const rejected = expect(pending).rejects.toThrow("시간 초과");
    await vi.advanceTimersByTimeAsync(10001);
    await rejected;
    expect(TestWorker.current.terminate).toHaveBeenCalledOnce();
  });
});
