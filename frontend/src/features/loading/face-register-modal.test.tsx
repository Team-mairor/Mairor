// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FaceRegisterModal } from "./face-register-modal";

const mocks = vi.hoisted(() => ({
  camera: { status: "ready", start: vi.fn(), videoRef: { current: {} } },
  frame: { current: null },
  passedNow: () => true,
  capture: vi.fn(),
  save: vi.fn(),
}));
vi.mock("@/features/face", () => ({
  CHECKS: ["light", "distance", "front", "clear"],
  DISTANCE_HINT_TEXT: {},
  allPassed: (check: Record<string, boolean>) => Object.values(check).every(Boolean),
  captureFace: mocks.capture,
  eyesClosed: () => false,
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
vi.mock("@/features/live", () => ({ useCameraErrorNote: () => null }));
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
  await act(async () => root.unmount());
  element.remove();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("얼굴 등록 완료 안내", () => {
  it.each([
    [false, "등록 완료 · 파우치 확인"],
    [true, "등록 완료"],
  ] as const)("파우치 확인 여부 %s에 맞는 다음 동작을 안내한다", async (pouchReviewed, label) => {
    const onDone = vi.fn();
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
