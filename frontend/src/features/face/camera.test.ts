// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";

import { exposureRange, matchExposure } from "./camera";

const track = (capabilities: Record<string, unknown>, settings: Record<string, unknown> = {}) =>
  ({
    getCapabilities: () => capabilities,
    getSettings: () => settings,
    applyConstraints: vi.fn(() => Promise.resolve()),
  }) as unknown as MediaStreamTrack;

describe("카메라 노출 맞추기", () => {
  it("최솟값과 최댓값이 모두 숫자인 노출 범위만 사용한다", () => {
    expect(exposureRange(track({ exposureTime: { min: 1, max: 1000 } }))).toEqual({
      min: 1,
      max: 1000,
    });
    expect(exposureRange(track({ exposureTime: { min: 1 } }))).toBeNull();
    expect(exposureRange(track({ exposureTime: { min: 1000, max: 1 } }))).toBeNull();
  });

  it("노출 시간이나 ISO 범위가 불완전하면 현재 값 잠금으로 대체한다", async () => {
    const camera = track(
      {
        exposureMode: ["continuous", "manual"],
        exposureTime: { min: 1 },
        iso: { min: 100, max: 800 },
      },
      { exposureTime: 0 },
    );

    await expect(matchExposure(camera, document.createElement("video"))).resolves.toEqual({
      exposure: "고정 안 함 (기기가 현재 값을 알려 주지 않음)",
    });
    expect(camera.applyConstraints).not.toHaveBeenCalled();
  });

  it("취소된 잠금은 카메라 제약을 더 적용하지 않는다", async () => {
    const controller = new AbortController();
    const camera = track({
      exposureMode: ["continuous", "manual"],
      exposureTime: { min: 1, max: 1000 },
      iso: { min: 100, max: 800 },
    });
    controller.abort();

    await expect(
      matchExposure(camera, document.createElement("video"), controller.signal),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(camera.applyConstraints).not.toHaveBeenCalled();
  });

  it("제약 적용 중 취소되면 다음 수동 노출을 적용하지 않는다", async () => {
    const controller = new AbortController();
    const camera = track({
      exposureMode: ["continuous", "manual"],
      exposureTime: { min: 1, max: 1000 },
      iso: { min: 100, max: 800 },
    });
    vi.mocked(camera.applyConstraints).mockImplementationOnce(async () => {
      controller.abort();
    });

    await expect(
      matchExposure(camera, document.createElement("video"), controller.signal),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(camera.applyConstraints).toHaveBeenCalledTimes(1);
  });

  it("마지막에 계산만 한 후보가 최적값이어도 실제 카메라에 다시 적용한다", async () => {
    let clock = 0;
    vi.spyOn(performance, "now").mockImplementation(() => (clock += 600));
    const brightness = [40, 20, 44, 44, 20];
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      drawImage: () => {},
      getImageData: () => {
        const value = brightness.shift()!;
        return { data: new Uint8ClampedArray([value, value, value, 255]) };
      },
    } as unknown as CanvasRenderingContext2D);
    const video = {
      requestVideoFrameCallback: (callback: VideoFrameRequestCallback) => {
        callback(0, {} as VideoFrameCallbackMetadata);
        return 1;
      },
      cancelVideoFrameCallback: () => {},
    } as unknown as HTMLVideoElement;
    const camera = track({
      exposureMode: ["continuous", "manual"],
      exposureTime: { min: 1, max: 1000, step: 1 },
      iso: { min: 100, max: 800 },
    });

    await matchExposure(camera, video);

    const applied = vi
      .mocked(camera.applyConstraints)
      .mock.calls.map(([constraints]) => constraints?.advanced?.[0]);
    expect(applied.at(-2)).toMatchObject({ exposureMode: "manual", exposureTime: 658 });
    expect(applied.at(-1)).toMatchObject({ exposureMode: "manual", exposureTime: 1000 });
  });

  it("영상 프레임이 오지 않으면 계속 기다리지 않고 자동 노출로 되돌린 뒤 실패를 알린다", async () => {
    vi.restoreAllMocks();
    vi.useFakeTimers();
    const video = {
      requestVideoFrameCallback: () => 1,
      cancelVideoFrameCallback: vi.fn(),
    } as unknown as HTMLVideoElement;
    const camera = track({
      exposureMode: ["continuous", "manual"],
      exposureTime: { min: 1, max: 1000 },
      iso: { min: 100, max: 800 },
    });

    const result = matchExposure(camera, video);
    await vi.advanceTimersByTimeAsync(2000);

    await expect(result).resolves.toEqual({ exposure: "실패: 영상 프레임이 오지 않습니다" });
    expect(video.cancelVideoFrameCallback).toHaveBeenCalled();
    const applied = vi
      .mocked(camera.applyConstraints)
      .mock.calls.map(([constraints]) => constraints?.advanced?.[0]);
    expect(applied.at(-1)).toMatchObject({ exposureMode: "continuous" });
    vi.useRealTimers();
  });
});
