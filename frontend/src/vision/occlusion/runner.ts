import type { OcclusionProvider, OcclusionRequest, OcclusionResponse } from "./messages";
import { squareCropBox, toModelInput, type CropBox, type Point } from "./preprocess";

/** 가림 표(size × size, 가림이면 1)와 그 표가 놓인 사진 자리 */
export interface OcclusionResult {
  size: number;
  data: Uint8Array;
  box: CropBox;
}

export interface OcclusionStatus {
  state: "idle" | "loading" | "on" | "off";
  provider: OcclusionProvider | null;
  /** 모델 한 번 도는 시간 가운데 값(ms)과 지금 쓰는 실행 간격(ms) */
  runMs: number | null;
  intervalMs: number | null;
  /** off일 때 이유 */
  reason: string | null;
}

/** 사진 한 장을 모델 입력(채널 먼저 float32)과 그 자리(상자)로 만든다. 테스트에서는 가짜를 넣는다 */
export type InputBuilder = (
  source: HTMLVideoElement,
  landmarks: readonly Point[],
  size: number,
) => { input: Float32Array; box: CropBox } | null;

export interface OcclusionRunnerOptions {
  createWorker?: () => Worker;
  buildInput?: InputBuilder;
  /** 시도할 방식 순서. 없으면 detectProviders로 정한다 */
  providers?: OcclusionProvider[];
  /** 시도할 방식 순서를 정하는 함수. 테스트에서 가짜를 넣는다 */
  detectProviders?: () => Promise<OcclusionProvider[]>;
  /** 입력 한 변. 없으면 방식별 기본값(INPUT_SIZE_BY_PROVIDER) */
  size?: number;
}

/**
 * 직전 가림 표를 쓰는 최소 나이 한도(ms). 실행 간격이 길면 그 두 배까지 늘린다.
 * 이보다 오래되면 가림 정보가 없는 것으로 본다
 */
export const MAX_MASK_AGE_MS = 1500;
/**
 * 방식별 입력 한 변. WebGPU는 384, wasm은 320이다. 갤럭시탭 S6 wasm 한 스레드 실측(2026-11-17)이
 * 384에서 한 장 약 1.27초, 320에서 약 0.91초이고, 320도 입 가림 판정이 384와 97.8% 같다(DEMO_AI_CHECK)
 */
export const INPUT_SIZE_BY_PROVIDER: Record<OcclusionProvider, number> = { webgpu: 384, wasm: 320 };
/** 방식마다 가장 짧은 실행 간격(ms). 실제로는 처리 시간의 1.5배보다 짧아지지 않는다 */
const BASE_INTERVAL_MS: Record<OcclusionProvider, number> = { webgpu: 200, wasm: 600 };
/** 한 번 도는 시간 가운데 값이 이보다 길면 가림 찾기를 끈다(게이지와 얼굴 추적을 막지 않으려고) */
export const TOO_SLOW_MS = 2000;
const HISTORY = 5;
const RUN_TIMEOUT_MS = 15_000;
const MAX_FAILURES = 3;

const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = sorted.length / 2;
  return sorted.length % 2 ? sorted[Math.floor(mid)] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/**
 * 쓸 수 있는 방식을 순서대로 고른다. 모델이 16비트 숫자(f16)를 쓰는데 WebGPU 어댑터가 f16 셰이더(shader-f16)를
 * 지원해야 모델을 열 수 있어서, 그것까지 확인한 뒤에만 WebGPU를 시도한다(갤럭시탭 S6의 Adreno 6xx는 지원하지 않는다)
 */
export async function detectProviders(): Promise<OcclusionProvider[]> {
  try {
    const gpu = (
      navigator as {
        gpu?: {
          requestAdapter: () => Promise<{ features: { has: (f: string) => boolean } } | null>;
        };
      }
    ).gpu;
    const adapter = await gpu?.requestAdapter();
    if (adapter?.features.has("shader-f16")) return ["webgpu", "wasm"];
  } catch {
    // WebGPU를 쓸 수 없으면 wasm으로 간다
  }
  return ["wasm"];
}

/** 영상 한 장에서 얼굴 상자를 정사각형으로 잘라 size × size로 줄인 모델 입력을 만든다 */
export const buildInputFromVideo: InputBuilder = (video, landmarks, size) => {
  const width = video.videoWidth;
  const height = video.videoHeight;
  if (!width || !height) return null;
  // 얼굴 점은 0~1이라 영상 크기를 곱한 픽셀 상자로 자른다
  const pixelBox = squareCropBox(landmarks, width, height);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return null;
  // 사진 밖은 검정(0)이다. 소스 상자가 영상을 벗어나면 겹치는 곳만 대응하는 자리에 그려진다
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, size, size);
  ctx.drawImage(video, pixelBox.left, pixelBox.top, pixelBox.side, pixelBox.side, 0, 0, size, size);
  return { input: toModelInput(ctx.getImageData(0, 0, size, size).data, size), box: pixelBox };
};

/**
 * 가림 찾기 모델을 워커에서 주기적으로 돌려 가장 최근 가림 표를 들고 있는다.
 * feed로 영상을 넘기면 돌릴 때가 됐을 때만 한 장을 보내고, 처리 시간에 맞춰 간격을 늘린다.
 * 모델을 못 열거나 너무 느리면 스스로 꺼서(off) 게이지가 가림 정보 없이 지금처럼 동작하게 한다
 */
export class OcclusionRunner {
  private worker: Worker | null = null;
  private queue: OcclusionProvider[];
  private provider: OcclusionProvider | null = null;
  private ready = false;
  private busy: { id: number; box: CropBox; sentAt: number } | null = null;
  private nextId = 0;
  private nextAt = 0;
  private latest: { result: OcclusionResult; at: number } | null = null;
  private times: number[] = [];
  private failures = 0;
  private current: OcclusionStatus = {
    state: "idle",
    provider: null,
    runMs: null,
    intervalMs: null,
    reason: null,
  };

  constructor(private readonly options: OcclusionRunnerOptions = {}) {
    this.queue = options.providers ? [...options.providers] : [];
  }

  get status(): OcclusionStatus {
    return this.current;
  }

  /** 모델을 연다. 이미 열었거나 열고 있으면 아무것도 하지 않는다 */
  start() {
    if (this.current.state !== "idle") return;
    if (this.options.providers) {
      this.openNext();
      return;
    }
    // 쓸 수 있는 방식을 알아내는 동안은 열고 있는 것으로 둔다
    this.current = { ...this.current, state: "loading" };
    void (this.options.detectProviders ?? detectProviders)().then((list) => {
      // 그 사이 닫혔으면 아무것도 하지 않는다
      if (this.current.state !== "loading" || this.worker) return;
      this.queue = [...list];
      this.openNext();
    });
  }

  /** 지금 쓸 수 있는 가림 표. 꺼져 있거나 너무 오래됐으면 null(가림 정보 없음) */
  latestFor(now: number): OcclusionResult | null {
    if (this.current.state !== "on" || !this.latest) return null;
    const maxAge = Math.max(MAX_MASK_AGE_MS, 2 * (this.current.intervalMs ?? 0));
    return now - this.latest.at <= maxAge ? this.latest.result : null;
  }

  /** 돌릴 때가 됐고 쉬는 중이면 이 영상 한 장을 보낸다 */
  feed(video: HTMLVideoElement, landmarks: readonly Point[], now: number) {
    const { state } = this.current;
    if (state === "idle") this.start();
    if (!this.worker || !this.ready || state === "off") return;
    if (this.busy) {
      // 응답이 오지 않으면 막힌 것으로 보고 끈다
      if (now - this.busy.sentAt > RUN_TIMEOUT_MS) this.turnOff("응답이 오지 않음");
      return;
    }
    if (now < this.nextAt) return;
    const size = this.options.size ?? INPUT_SIZE_BY_PROVIDER[this.provider ?? "wasm"];
    const built = (this.options.buildInput ?? buildInputFromVideo)(video, landmarks, size);
    if (!built) return;
    const id = this.nextId++;
    this.busy = { id, box: built.box, sentAt: now };
    const message: OcclusionRequest = {
      type: "run",
      id,
      size,
      input: built.input,
    };
    this.worker.postMessage(message, [built.input.buffer]);
  }

  dispose() {
    this.worker?.terminate();
    this.worker = null;
    this.ready = false;
    this.busy = null;
    this.latest = null;
    this.current = { ...this.current, state: "off", reason: this.current.reason ?? "닫음" };
  }

  private openNext() {
    const provider = this.queue.shift();
    this.worker?.terminate();
    this.worker = null;
    this.ready = false;
    if (!provider) {
      this.turnOff(this.current.reason ?? "모델을 열지 못함");
      return;
    }
    this.provider = provider;
    this.current = { ...this.current, state: "loading", provider, reason: null };
    let worker: Worker;
    try {
      worker =
        this.options.createWorker?.() ??
        new Worker(new URL("./occlusion.worker.ts", import.meta.url), { type: "module" });
    } catch (e) {
      // 워커를 못 만드는 환경이면 가림 찾기 없이 간다
      this.current = { ...this.current, reason: e instanceof Error ? e.message : String(e) };
      this.openNext();
      return;
    }
    this.worker = worker;
    worker.onmessage = (event: MessageEvent<OcclusionResponse>) => this.onMessage(event.data);
    worker.onerror = (event) => this.onFailure(event.message || "워커 오류");
    const init: OcclusionRequest = { type: "init", provider };
    worker.postMessage(init);
  }

  private onMessage(message: OcclusionResponse) {
    if (message.type === "ready") {
      this.ready = true;
      this.times = [];
      this.failures = 0;
      this.current = { ...this.current, state: "on", provider: message.provider, reason: null };
      return;
    }
    if (message.type === "error") {
      this.onFailure(message.message);
      return;
    }
    const busy = this.busy;
    if (!busy || busy.id !== message.id) return;
    this.busy = null;
    this.failures = 0;
    const size = Math.round(Math.sqrt(message.mask.length));
    // 가림 표의 나이는 그 영상을 보낸 때부터 센다
    this.latest = { result: { size, data: message.mask, box: busy.box }, at: busy.sentAt };
    this.times = [...this.times, message.runMs + message.postMs].slice(-HISTORY);
    const runMs = median(this.times);
    const provider = this.provider ?? "wasm";
    const intervalMs = Math.max(BASE_INTERVAL_MS[provider], Math.round(runMs * 1.5));
    this.nextAt = busy.sentAt + intervalMs;
    this.current = { ...this.current, runMs: Math.round(runMs), intervalMs };
    if (this.times.length >= 3 && runMs > TOO_SLOW_MS)
      this.turnOff(`너무 느림(${Math.round(runMs)}ms)`);
  }

  private onFailure(reason: string) {
    this.busy = null;
    if (!this.ready) {
      // 모델을 여는 중 실패하면 다음 방식으로 넘어간다(WebGPU → wasm)
      this.current = { ...this.current, reason };
      this.openNext();
      return;
    }
    if (++this.failures >= MAX_FAILURES) this.turnOff(reason);
  }

  private turnOff(reason: string) {
    this.worker?.terminate();
    this.worker = null;
    this.ready = false;
    this.busy = null;
    this.current = { ...this.current, state: "off", reason };
  }
}
