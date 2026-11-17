"use client";

import { useEffect, useRef, useState } from "react";

import {
  OCCLUSION_MODEL_URL,
  squareCropBox,
  toModelInput,
  type OcclusionProvider,
  type OcclusionRequest,
  type OcclusionResponse,
} from "@/vision/occlusion";

import { compareMasks, summarize, type Summary } from "./bench-stats";

/**
 * 가림 찾기 모델 속도 측정(개발 화면). 카메라 없이 사진 한 장으로 WebGPU · wasm × 입력 384 · 320을 재고
 * 결과를 window.__OCC_BENCH__에 둔다. 태블릿에서는 scripts/occlusion-bench.mjs가 이 값을 읽어 온다.
 * 열 때 ?auto=1을 붙이면 바로 시작한다
 */
const SAMPLE_IMAGE = "/images/how-it-works-face.png";
/** 샘플 사진에서 얼굴이 있는 자리(0~1). 속도 측정용이라 대략이면 된다 */
const FACE_POINTS = [
  { x: 0.29, y: 0.17 },
  { x: 0.85, y: 0.93 },
];
const PROVIDERS: OcclusionProvider[] = ["webgpu", "wasm"];
const SIZES = [384, 320];
const WARMUP = 2;
const RUNS = 15;
const CALL_TIMEOUT_MS = 120_000;

interface RunResult {
  provider: OcclusionProvider;
  size: number;
  ok: boolean;
  error?: string;
  loadMs?: number;
  /** 모델 한 번 도는 시간(출력 읽기까지)과 가림 고르기 시간, 요청부터 응답까지 전체 시간 */
  runMs?: Summary | null;
  postMs?: Summary | null;
  wallMs?: Summary | null;
  /** 사진 자르기 · 줄이기 · 정규화에 걸린 시간 */
  preMs?: number;
  occludedShare?: number;
}

export interface BenchResult {
  version: 1;
  startedAt: string;
  finishedAt?: string;
  done: boolean;
  env: Record<string, unknown>;
  modelBytes: number | null;
  runs: RunResult[];
  agreement: { size: number; samePixels: number; iou: number | null }[];
  error?: string;
}

declare global {
  interface Window {
    __OCC_BENCH__?: BenchResult;
    __OCC_BENCH_STATE__?: string;
  }
}

interface GpuAdapterLike {
  info?: Record<string, unknown>;
  requestAdapterInfo?: () => Promise<Record<string, unknown>>;
  isFallbackAdapter?: boolean;
  features?: { has: (feature: string) => boolean } & Iterable<string>;
  limits?: { maxBufferSize?: number };
}

async function environment(): Promise<Record<string, unknown>> {
  const nav = navigator as Navigator & {
    deviceMemory?: number;
    gpu?: { requestAdapter: () => Promise<GpuAdapterLike | null> };
  };
  let gpu: Record<string, unknown> = { api: Boolean(nav.gpu) };
  if (nav.gpu) {
    try {
      const adapter = await nav.gpu.requestAdapter();
      if (!adapter) gpu = { api: true, adapter: false };
      else {
        const info = adapter.info ?? (await adapter.requestAdapterInfo?.()) ?? {};
        gpu = {
          api: true,
          adapter: true,
          vendor: info.vendor,
          architecture: info.architecture,
          device: info.device,
          description: info.description,
          isFallbackAdapter: adapter.isFallbackAdapter,
          // 16비트 모델은 shader-f16이 있어야 WebGPU로 열린다
          shaderF16: adapter.features?.has("shader-f16") ?? false,
          features: adapter.features ? Array.from(adapter.features) : [],
          maxBufferSize: adapter.limits?.maxBufferSize,
        };
      }
    } catch (e) {
      gpu = { api: true, error: e instanceof Error ? e.message : String(e) };
    }
  }
  return {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemoryGb: nav.deviceMemory ?? null,
    crossOriginIsolated: window.crossOriginIsolated,
    secureContext: window.isSecureContext,
    screen: `${screen.width}x${screen.height}@${window.devicePixelRatio}`,
    gpu,
  };
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`사진을 불러오지 못했습니다: ${src}`));
    img.src = src;
  });
}

function buildInput(img: HTMLImageElement, size: number): Float32Array {
  const box = squareCropBox(FACE_POINTS, img.naturalWidth, img.naturalHeight);
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("캔버스를 만들지 못했습니다");
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, size, size);
  ctx.drawImage(img, box.left, box.top, box.side, box.side, 0, 0, size, size);
  return toModelInput(ctx.getImageData(0, 0, size, size).data, size);
}

function call(worker: Worker, message: OcclusionRequest): Promise<OcclusionResponse> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      worker.removeEventListener("message", onMessage);
      reject(new Error(`응답이 ${CALL_TIMEOUT_MS / 1000}초 안에 오지 않았습니다`));
    }, CALL_TIMEOUT_MS);
    const onMessage = (event: MessageEvent<OcclusionResponse>) => {
      clearTimeout(timer);
      worker.removeEventListener("message", onMessage);
      resolve(event.data);
    };
    worker.addEventListener("message", onMessage);
    worker.postMessage(message);
  });
}

async function runBench(report: (text: string) => void): Promise<BenchResult> {
  const result: BenchResult = {
    version: 1,
    startedAt: new Date().toISOString(),
    done: false,
    env: await environment(),
    modelBytes: null,
    runs: [],
    agreement: [],
  };
  window.__OCC_BENCH__ = result;
  try {
    const head = await fetch(OCCLUSION_MODEL_URL, { method: "HEAD" });
    result.modelBytes = head.ok ? Number(head.headers.get("content-length")) || null : null;
    const img = await loadImage(SAMPLE_IMAGE);
    const masks = new Map<string, Uint8Array>();

    for (const provider of PROVIDERS) {
      report(`${provider}: 모델을 여는 중`);
      const worker = new Worker(
        new URL("../../../vision/occlusion/occlusion.worker.ts", import.meta.url),
        { type: "module" },
      );
      try {
        const ready = await call(worker, { type: "init", provider });
        if (ready.type !== "ready") {
          const error = ready.type === "error" ? ready.message : "알 수 없는 응답";
          for (const size of SIZES) result.runs.push({ provider, size, ok: false, error });
          continue;
        }
        for (const size of SIZES) {
          const entry: RunResult = { provider, size, ok: true, loadMs: Math.round(ready.ms) };
          result.runs.push(entry);
          const preStarted = performance.now();
          let input = buildInput(img, size);
          for (let i = 0; i < 4; i++) input = buildInput(img, size);
          entry.preMs = Math.round(((performance.now() - preStarted) / 5) * 10) / 10;

          const runMs: number[] = [];
          const postMs: number[] = [];
          const wallMs: number[] = [];
          for (let i = 0; i < WARMUP + RUNS; i++) {
            report(
              `${provider} ${size}: ${i < WARMUP ? "예열" : "측정"} ${i + 1}/${WARMUP + RUNS}`,
            );
            const started = performance.now();
            const reply = await call(worker, { type: "run", id: i, size, input });
            const wall = performance.now() - started;
            if (reply.type !== "result") {
              entry.ok = false;
              entry.error = reply.type === "error" ? reply.message : "알 수 없는 응답";
              break;
            }
            if (i >= WARMUP) {
              runMs.push(reply.runMs);
              postMs.push(reply.postMs);
              wallMs.push(wall);
            }
            if (i === WARMUP + RUNS - 1) {
              masks.set(`${provider}-${size}`, reply.mask);
              let on = 0;
              for (const v of reply.mask) on += v;
              entry.occludedShare = Math.round((on / reply.mask.length) * 10000) / 10000;
            }
          }
          entry.runMs = summarize(runMs);
          entry.postMs = summarize(postMs);
          entry.wallMs = summarize(wallMs);
        }
      } catch (e) {
        const error = e instanceof Error ? e.message : String(e);
        for (const size of SIZES) {
          const prev = result.runs.find((r) => r.provider === provider && r.size === size);
          // 재는 중에 예외가 난 항목(runMs 없음)은 실패로 고친다. 이미 끝난 항목은 그대로 둔다
          if (!prev) result.runs.push({ provider, size, ok: false, error });
          else if (prev.ok && !prev.runMs) {
            prev.ok = false;
            prev.error = error;
          }
        }
      } finally {
        worker.terminate();
      }
    }

    for (const size of SIZES) {
      const a = masks.get(`webgpu-${size}`);
      const b = masks.get(`wasm-${size}`);
      if (a && b) result.agreement.push({ size, ...compareMasks(a, b) });
    }
  } catch (e) {
    result.error = e instanceof Error ? e.message : String(e);
  }
  result.finishedAt = new Date().toISOString();
  result.done = true;
  report("끝");
  return result;
}

export default function OcclusionBenchPage() {
  const [status, setStatus] = useState("대기 중");
  const [result, setResult] = useState<BenchResult | null>(null);
  const running = useRef(false);

  const start = async () => {
    if (running.current) return;
    running.current = true;
    setResult(null);
    const report = (text: string) => {
      window.__OCC_BENCH_STATE__ = text;
      setStatus(text);
    };
    const done = await runBench(report);
    setResult({ ...done });
    running.current = false;
  };

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("auto") === "1") {
      // 주소에 ?auto=1이 있으면 열자마자 측정을 시작한다
      void start();
    }
  }, []);

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 p-6 text-sm">
      <h1 className="text-xl font-bold">가림 찾기 모델 속도 측정</h1>
      <p>
        카메라 없이 사진 한 장으로 WebGPU와 wasm, 입력 384와 320을 잽니다. 끝날 때까지 이 화면을 켜
        둔 채 다른 앱으로 나가지 마세요.
      </p>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void start()}
          className="rounded border px-3 py-1.5 font-semibold"
        >
          측정 시작
        </button>
        <span data-bench-status>{status}</span>
      </div>
      {result && (
        <>
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b">
                <th>방식</th>
                <th>입력</th>
                <th>열기(ms)</th>
                <th>한 장 가운데(ms)</th>
                <th>90%(ms)</th>
                <th>결과</th>
              </tr>
            </thead>
            <tbody>
              {result.runs.map((r) => (
                <tr key={`${r.provider}-${r.size}`} className="border-b">
                  <td>{r.provider}</td>
                  <td>{r.size}</td>
                  <td>{r.loadMs ?? "-"}</td>
                  <td>{r.runMs?.median ?? "-"}</td>
                  <td>{r.runMs?.p90 ?? "-"}</td>
                  <td>{r.ok ? "정상" : (r.error ?? "실패")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <textarea
            readOnly
            data-bench-json
            className="h-64 w-full rounded border p-2 font-mono text-xs"
            value={JSON.stringify(result, null, 2)}
          />
        </>
      )}
    </main>
  );
}
