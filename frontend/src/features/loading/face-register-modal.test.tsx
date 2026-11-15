// @vitest-environment jsdom
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FaceRegisterModal } from "./face-register-modal";

const mocks = vi.hoisted(() => ({
  camera: { status: "ready", start: vi.fn(), videoRef: { current: {} } },
  frame: { current: null as object | null },
  passedNow: () => true,
  capture: vi.fn(),
  save: vi.fn(),
  pixels: vi.fn(),
  saveBrows: vi.fn(),
}));
vi.mock("@/features/face", () => ({
  CHECKS: ["light", "distance", "front", "clear"],
  DISTANCE_HINT_TEXT: {},
  allPassed: (check: Record<string, boolean>) => Object.values(check).every(Boolean),
  captureFace: mocks.capture,
  eyesClosed: () => false,
  hasMirrorFit: () => true,
  loadMirrorFit: () => null,
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
vi.mock("@/features/guide", () => ({
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
    await register();
    expect(mocks.save).toHaveBeenCalledOnce();
    expect(mocks.saveBrows).not.toHaveBeenCalled();
  });
});
