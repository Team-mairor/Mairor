import { describe, expect, it } from "vitest";

import type { OcclusionRequest, OcclusionResponse } from "./messages";
import {
  detectProviders,
  INPUT_SIZE_BY_PROVIDER,
  MAX_MASK_AGE_MS,
  OcclusionRunner,
  TOO_SLOW_MS,
  type InputBuilder,
} from "./runner";

/** 보낸 요청을 기록하고, 테스트가 응답을 직접 돌려주는 가짜 워커 */
class FakeWorker {
  sent: OcclusionRequest[] = [];
  terminated = false;
  onmessage: ((event: MessageEvent<OcclusionResponse>) => void) | null = null;
  onerror: ((event: { message: string }) => void) | null = null;
  postMessage(message: OcclusionRequest) {
    this.sent.push(message);
  }
  terminate() {
    this.terminated = true;
  }
  reply(message: OcclusionResponse) {
    this.onmessage?.({ data: message } as MessageEvent<OcclusionResponse>);
  }
  get inits() {
    return this.sent.filter((m) => m.type === "init");
  }
  get runs() {
    return this.sent.filter((m) => m.type === "run");
  }
}

const SIZE = 8;
const buildInput: InputBuilder = () => ({
  input: new Float32Array(3 * SIZE * SIZE),
  box: { left: 10, top: 20, side: 100 },
});
const video = {} as HTMLVideoElement;
const face = [{ x: 0.5, y: 0.5 }];

function setup(providers: ("webgpu" | "wasm")[]) {
  const workers: FakeWorker[] = [];
  const runner = new OcclusionRunner({
    providers,
    size: SIZE,
    buildInput,
    createWorker: () => {
      const w = new FakeWorker();
      workers.push(w);
      return w as unknown as Worker;
    },
  });
  return { runner, workers, last: () => workers[workers.length - 1] };
}

const ready = (provider: "webgpu" | "wasm") =>
  ({ type: "ready", provider, ms: 100, inputName: "input", outputName: "logits" }) as const;
const result = (id: number, runMs: number, on = 0): OcclusionResponse => {
  const mask = new Uint8Array(SIZE * SIZE);
  mask.fill(on);
  return { type: "result", id, mask, runMs, postMs: 0 };
};

describe("가림 찾기 실행기", () => {
  it("처음 feed에서 모델을 열고, 준비되면 한 장씩 보낸다", () => {
    const { runner, last } = setup(["wasm"]);
    runner.feed(video, face, 0);
    expect(last().inits).toEqual([{ type: "init", provider: "wasm" }]);
    expect(runner.status.state).toBe("loading");

    // 준비 전에는 보내지 않는다
    runner.feed(video, face, 10);
    expect(last().runs).toHaveLength(0);

    last().reply(ready("wasm"));
    expect(runner.status.state).toBe("on");
    runner.feed(video, face, 20);
    expect(last().runs).toHaveLength(1);
  });

  it("WebGPU를 못 열면 wasm으로 넘어간다", () => {
    const { runner, workers, last } = setup(["webgpu", "wasm"]);
    runner.start();
    expect(workers[0].inits[0]).toEqual({ type: "init", provider: "webgpu" });
    workers[0].reply({ type: "error", message: "no webgpu" });

    expect(workers[0].terminated).toBe(true);
    expect(workers).toHaveLength(2);
    expect(last().inits[0]).toEqual({ type: "init", provider: "wasm" });
    last().reply(ready("wasm"));
    expect(runner.status).toMatchObject({ state: "on", provider: "wasm" });
  });

  it("모든 방식이 실패하면 꺼지고 이유를 남긴다", () => {
    const { runner, workers } = setup(["webgpu", "wasm"]);
    runner.start();
    workers[0].reply({ type: "error", message: "a" });
    workers[1].reply({ type: "error", message: "b" });
    expect(runner.status).toMatchObject({ state: "off", reason: "b" });
    expect(runner.latestFor(0)).toBeNull();
  });

  it("처리 시간의 1.5배와 방식별 최소 간격 가운데 긴 쪽으로 간격을 둔다", () => {
    const { runner, last } = setup(["wasm"]);
    runner.start();
    last().reply(ready("wasm"));
    runner.feed(video, face, 0);
    last().reply(result(0, 100));
    // wasm 최소 600ms
    expect(runner.status.intervalMs).toBe(600);
    runner.feed(video, face, 599);
    expect(last().runs).toHaveLength(1);
    runner.feed(video, face, 600);
    expect(last().runs).toHaveLength(2);

    // 처리 시간 가운데 값이 550ms가 되면 간격은 825ms(600보다 길어짐)
    last().reply(result(1, 1000));
    expect(runner.status).toMatchObject({ runMs: 550, intervalMs: 825 });
    runner.feed(video, face, 1424);
    expect(last().runs).toHaveLength(2);
    runner.feed(video, face, 1425);
    expect(last().runs).toHaveLength(3);

    // 가운데 값이 1,000ms가 되면 1,500ms
    last().reply(result(2, 1000));
    expect(runner.status).toMatchObject({ runMs: 1000, intervalMs: 1500 });
  });

  it("WebGPU는 0.2초 간격까지 짧게 돈다", () => {
    const { runner, last } = setup(["webgpu"]);
    runner.start();
    last().reply(ready("webgpu"));
    runner.feed(video, face, 0);
    last().reply(result(0, 40));
    expect(runner.status.intervalMs).toBe(200);
  });

  it("직전 가림 표를 쓰다가 너무 오래되면 가림 정보가 없는 것으로 본다", () => {
    const { runner, last } = setup(["wasm"]);
    runner.start();
    last().reply(ready("wasm"));
    runner.feed(video, face, 1000);
    last().reply(result(0, 100, 1));

    const fresh = runner.latestFor(1000 + MAX_MASK_AGE_MS);
    expect(fresh).toMatchObject({ size: SIZE, box: { left: 10, top: 20, side: 100 } });
    expect(fresh?.data.every((v) => v === 1)).toBe(true);
    expect(runner.latestFor(1000 + MAX_MASK_AGE_MS + 1)).toBeNull();
  });

  it("처리 시간 가운데 값이 너무 길면 스스로 끈다", () => {
    const { runner, last, workers } = setup(["wasm"]);
    runner.start();
    last().reply(ready("wasm"));
    let now = 0;
    for (let i = 0; i < 3; i++) {
      runner.feed(video, face, now);
      last().reply(result(i, TOO_SLOW_MS + 500));
      now += 10_000;
    }
    expect(runner.status.state).toBe("off");
    expect(runner.status.reason).toContain("너무 느림");
    expect(workers[0].terminated).toBe(true);
    // 꺼진 뒤에는 보내지 않고 가림 정보도 없다
    runner.feed(video, face, now);
    expect(last().runs).toHaveLength(3);
    expect(runner.latestFor(now)).toBeNull();
  });

  it("응답이 오래 오지 않으면 막힌 것으로 보고 끈다", () => {
    const { runner, last } = setup(["wasm"]);
    runner.start();
    last().reply(ready("wasm"));
    runner.feed(video, face, 0);
    runner.feed(video, face, 14_000);
    expect(runner.status.state).toBe("on");
    runner.feed(video, face, 15_001);
    expect(runner.status).toMatchObject({ state: "off", reason: "응답이 오지 않음" });
  });

  it("돌리는 중 오류가 연달아 나면 끈다", () => {
    const { runner, last } = setup(["wasm"]);
    runner.start();
    last().reply(ready("wasm"));
    let now = 0;
    for (let i = 0; i < 3; i++) {
      runner.feed(video, face, now);
      last().reply({ type: "error", id: i, message: "run failed" });
      now += 10_000;
    }
    expect(runner.status).toMatchObject({ state: "off", reason: "run failed" });
  });

  it("dispose하면 워커를 끝내고 꺼진다", () => {
    const { runner, workers } = setup(["wasm"]);
    runner.start();
    runner.dispose();
    expect(workers[0].terminated).toBe(true);
    expect(runner.status.state).toBe("off");
  });

  it("실행 간격이 길면 가림 표를 간격의 두 배까지 쓴다", () => {
    const { runner, last } = setup(["wasm"]);
    runner.start();
    last().reply(ready("wasm"));
    runner.feed(video, face, 1000);
    // 처리 시간 1,500ms → 간격 2,250ms → 유효 4,500ms
    last().reply(result(0, 1500, 1));
    expect(runner.status.intervalMs).toBe(2250);
    expect(runner.latestFor(1000 + 4500)).not.toBeNull();
    expect(runner.latestFor(1000 + 4501)).toBeNull();
  });
});

describe("방식과 입력 크기 고르기", () => {
  it("방식별 입력 크기는 WebGPU 384, wasm 320이다", () => {
    expect(INPUT_SIZE_BY_PROVIDER).toEqual({ webgpu: 384, wasm: 320 });
  });

  it("크기를 따로 주지 않으면 지금 쓰는 방식의 입력 크기로 보낸다", async () => {
    const sizes: number[] = [];
    const workers: FakeWorker[] = [];
    const runner = new OcclusionRunner({
      detectProviders: async () => ["wasm"],
      buildInput: (_video, _landmarks, size) => {
        sizes.push(size);
        return { input: new Float32Array(3), box: { left: 0, top: 0, side: 10 } };
      },
      createWorker: () => {
        const w = new FakeWorker();
        workers.push(w);
        return w as unknown as Worker;
      },
    });
    runner.start();
    expect(runner.status.state).toBe("loading");
    await Promise.resolve();
    await Promise.resolve();
    workers[0].reply(ready("wasm"));
    runner.feed(video, face, 0);
    expect(sizes).toEqual([320]);
    expect(workers[0].runs[0]).toMatchObject({ size: 320 });
  });

  it("방식을 알아내는 동안 닫으면 모델을 열지 않는다", async () => {
    const workers: FakeWorker[] = [];
    const runner = new OcclusionRunner({
      detectProviders: async () => ["webgpu", "wasm"],
      createWorker: () => {
        const w = new FakeWorker();
        workers.push(w);
        return w as unknown as Worker;
      },
    });
    runner.start();
    runner.dispose();
    await Promise.resolve();
    await Promise.resolve();
    expect(workers).toHaveLength(0);
    expect(runner.status.state).toBe("off");
  });
});

describe("쓸 수 있는 방식 알아내기", () => {
  const withGpu = (gpu: unknown) => {
    Object.defineProperty(globalThis, "navigator", { value: { gpu }, configurable: true });
  };

  it("WebGPU 어댑터가 f16 셰이더를 지원하면 WebGPU → wasm 순서다", async () => {
    withGpu({ requestAdapter: async () => ({ features: new Set(["shader-f16"]) }) });
    expect(await detectProviders()).toEqual(["webgpu", "wasm"]);
  });

  it("f16 셰이더가 없으면(갤럭시탭 S6) wasm만 쓴다", async () => {
    withGpu({ requestAdapter: async () => ({ features: new Set(["timestamp-query"]) }) });
    expect(await detectProviders()).toEqual(["wasm"]);
  });

  it("어댑터가 없거나 WebGPU가 없거나 오류가 나도 wasm이다", async () => {
    withGpu({ requestAdapter: async () => null });
    expect(await detectProviders()).toEqual(["wasm"]);
    withGpu(undefined);
    expect(await detectProviders()).toEqual(["wasm"]);
    withGpu({
      requestAdapter: async () => {
        throw new Error("denied");
      },
    });
    expect(await detectProviders()).toEqual(["wasm"]);
  });
});
