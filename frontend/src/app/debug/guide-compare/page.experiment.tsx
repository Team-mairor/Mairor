"use client";

import { useEffect, useRef, useState } from "react";

import {
  CameraProvider,
  useCamera,
  useFaceFrame,
  useHiddenVideo,
  containTransform,
  toScreen,
  type FaceFrame,
} from "@/vision/face";
import { GuideRenderer, loadDefaultGuideSet, loadGuideSet, type GuideSet } from "@/vision/guide";
import { loadFaceMesh, type FaceMesh } from "@/vision/overlay";

import { fitDetectedBrows, type BrowDetection, type FaceCrop } from "./brow-geometry";
import type { BrowRequest, BrowResponse } from "./brow-messages";

const FACES = ["front", "turned-left", "close-up", "far", "blink-hold", "lost"];
const SEQUENCES: Record<string, string[]> = {
  "표시 → hold → lost → 복구": ["front", "blink-hold", "lost", "front"],
  "숨김 → hold": ["lost", "blink-hold"],
};

export default function Page() {
  const [source, setSource] = useState("synthetic");
  return (
    <main className="flex flex-1 flex-col gap-3 p-4">
      <h1 className="text-xl font-bold">기본 가이드 변경 전·후 · 268</h1>
      <p>같은 얼굴로 변경 전·현재 가이드를 비교합니다. 실제 회전은 카메라로 확인하세요.</p>
      <label>
        입력{" "}
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="synthetic">합성 얼굴</option>
          <option value="camera">실시간 카메라</option>
        </select>
      </label>
      <CameraProvider key={source} autoStart={source === "camera"} errorView="none">
        <Compare live={source === "camera"} />
      </CameraProvider>
    </main>
  );
}

function Compare({ live }: { live: boolean }) {
  useHiddenVideo();
  const { videoRef, status, error, start } = useCamera();
  const [part, setPart] = useState("blush");
  const [mode, setMode] = useState("current");
  const [face, setFace] = useState("front");
  const [message, setMessage] = useState("");
  const [ready, setReady] = useState(false);
  const [frozen, setFrozen] = useState(false);
  const [sequence, setSequence] = useState("");
  const [recognition, setRecognition] = useState(false);
  const [recognitionStatus, setRecognitionStatus] = useState("꺼짐");
  const [modelReady, setModelReady] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [showBoundary, setShowBoundary] = useState(true);
  const workerRef = useRef<Worker | null>(null);
  const detectedRef = useRef<BrowDetection | null>(null);
  const pendingRef = useRef<{ id: number; frame: FaceFrame; crop: FaceCrop } | null>(null);
  const recognitionRef = useRef(false);
  const requestIdRef = useRef(0);
  const boundaryRef = useRef(true);
  useEffect(() => {
    boundaryRef.current = showBoundary;
  }, [showBoundary]);
  const canvases = useRef<(HTMLCanvasElement | null)[]>([]);
  const backgrounds = useRef<(HTMLCanvasElement | null)[]>([]);
  const frameRef = useRef<FaceFrame | null>(null);
  const liveRef = useRef<FaceFrame | null>(null);
  const freezeRef = useRef(false);
  const frozenVideo = useRef<HTMLCanvasElement | null>(null);
  const state = useRef({ part, live, frozen });
  const data = useRef<{ mesh: FaceMesh; sets: GuideSet[] } | null>(null);
  useEffect(() => {
    state.current = { part, live, frozen };
  }, [part, live, frozen]);
  useFaceFrame((frame) => {
    liveRef.current = frame;
    if (!freezeRef.current) {
      frameRef.current = frame;
      if (
        (!frame || frame.trackingState === "lost") &&
        (detectedRef.current || pendingRef.current)
      ) {
        detectedRef.current = null;
        pendingRef.current = null;
        setDetecting(false);
        setRecognitionStatus("얼굴 추적을 놓쳤습니다. 정면에서 다시 인식해 주세요");
      }
    }
  });

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      loadFaceMesh(),
      loadDefaultGuideSet(),
      loadGuideSet("/fixtures/guides/compare-baseline.json"),
    ])
      .then(([mesh, current, baseline]) => {
        if (!cancelled) {
          data.current = {
            mesh,
            sets: [baseline, current],
          };
          setReady(true);
        }
      })
      .catch((e) => {
        if (!cancelled) setMessage(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (live) return;
    let cancelled = false;
    fetch(`/fixtures/faces/${face}.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`얼굴 로딩 실패: ${r.status}`);
        return r.json();
      })
      .then((frame) => {
        if (!cancelled) {
          frameRef.current = frame;
          setMessage("");
        }
      })
      .catch((e) => {
        if (!cancelled) {
          frameRef.current = null;
          setMessage(String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [face, live]);

  useEffect(() => {
    if (!sequence || live) return;
    const steps = SEQUENCES[sequence];
    let i = 0;
    setFace(steps[0]); // eslint-disable-line react-hooks/set-state-in-effect
    const timer = window.setInterval(() => {
      i += 1;
      if (i >= steps.length) {
        clearInterval(timer);
        setSequence("");
      } else setFace(steps[i]);
    }, 1000);
    return () => clearInterval(timer);
  }, [sequence, live]);

  useEffect(() => {
    if (!ready) return;
    const renderers = canvases.current.map(
      (c, i) => new GuideRenderer(c!, i === 0 ? 1.2 : undefined),
    );
    let raf = 0;
    const draw = (now: number) => {
      const frame = frameRef.current,
        loaded = data.current;
      if (loaded)
        renderers.forEach((renderer, i) => {
          const canvas = canvases.current[i]!,
            bg = backgrounds.current[i]!;
          const width = canvas.clientWidth,
            height = canvas.clientHeight,
            dpr = window.devicePixelRatio || 1;
          if (
            canvas.width !== Math.round(width * dpr) ||
            canvas.height !== Math.round(height * dpr)
          )
            renderer.resize(width, height, dpr);
          if (bg.width !== canvas.width || bg.height !== canvas.height) {
            bg.width = canvas.width;
            bg.height = canvas.height;
          }
          const ctx = bg.getContext("2d")!;
          ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
          ctx.clearRect(0, 0, width, height);
          const view = frame ? containTransform(frame.imageSize, { width, height }, true) : null;
          if (frame && view && state.current.live) {
            const video = state.current.frozen ? frozenVideo.current : videoRef.current;
            if (video) {
              ctx.save();
              ctx.translate(width, 0);
              ctx.scale(-1, 1);
              ctx.drawImage(
                video,
                view.offsetX,
                view.offsetY,
                frame.imageSize.width * view.scale,
                frame.imageSize.height * view.scale,
              );
              ctx.restore();
            }
          }
          const useDetection = i === 1 && state.current.part === "brow" && recognitionRef.current;
          const detection = detectedRef.current;
          let step = useDetection
            ? (detection?.step ?? null)
            : (loaded.sets[i].steps.find((s) => s.stepId === state.current.part) ?? null);
          if (step && useDetection && boundaryRef.current && detection)
            step = {
              ...step,
              guides: [
                ...step.guides,
                ...detection.outline.map((outline) => ({ type: "polygon" as const, outline })),
              ],
            };
          renderer.render({
            frame,
            mesh: loaded.mesh,
            step,
            projection:
              frame && view
                ? { toPx: (p) => toScreen(p, frame.imageSize, view), unit: frame.iod * view.scale }
                : null,
            now,
            face: !state.current.live,
          });
        });
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [ready, videoRef]);

  useEffect(() => {
    recognitionRef.current = recognition;
    detectedRef.current = null;
    pendingRef.current = null;
    if (!recognition) return;
    const worker = new Worker(new URL("./brow.worker.ts", import.meta.url), { type: "module" });
    workerRef.current = worker;
    worker.onmessage = (event: MessageEvent<BrowResponse>) => {
      if (event.data.type === "ready") {
        setModelReady(true);
        setRecognitionStatus("모델 준비됨 · 정면에서 ‘다시 인식’을 눌러 주세요");
      } else if (event.data.type === "result") {
        const pending = pendingRef.current;
        if (!pending || pending.id !== event.data.id) return;
        pendingRef.current = null;
        try {
          if (!pending || !data.current) return;
          detectedRef.current = fitDetectedBrows(
            event.data.mask,
            512,
            pending.crop,
            pending.frame,
            data.current.mesh,
          );
          setRecognitionStatus(
            `양쪽 눈썹 검출 · ${Math.round(event.data.ms)}ms · 얼굴 추적으로 유지 중`,
          );
        } catch (e) {
          setRecognitionStatus(String(e));
        } finally {
          setDetecting(false);
        }
      } else if (event.data.type === "error") {
        if (event.data.id !== undefined && pendingRef.current?.id !== event.data.id) return;
        pendingRef.current = null;
        setDetecting(false);
        setRecognitionStatus(`인식 오류: ${event.data.message}`);
      }
    };
    worker.onerror = (e) => {
      pendingRef.current = null;
      setDetecting(false);
      setRecognitionStatus(`모델 실행 오류: ${e.message}`);
    };
    worker.postMessage({ type: "init" } satisfies BrowRequest);
    return () => {
      worker.onmessage = null;
      worker.onerror = null;
      worker.terminate();
      workerRef.current = null;
      detectedRef.current = null;
      pendingRef.current = null;
    };
  }, [recognition]);

  const detectBrows = () => {
    const frame = frameRef.current;
    const source = frozen ? frozenVideo.current : videoRef.current;
    if (
      !frame ||
      !source ||
      frame.trackingState !== "tracking" ||
      Math.abs(frame.pose.yaw) > 0.2 ||
      Math.abs(frame.pose.pitch) > 0.2
    ) {
      setRecognitionStatus("양쪽 눈썹이 보이도록 정면을 보고 다시 인식해 주세요");
      return;
    }
    if (!workerRef.current || pendingRef.current) return;
    const { width, height } = frame.imageSize;
    const xs = frame.landmarks.slice(0, 468).map((p) => p.x * width),
      ys = frame.landmarks.slice(0, 468).map((p) => p.y * height);
    const size =
      Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 1.4;
    const crop = {
      x: (Math.min(...xs) + Math.max(...xs) - size) / 2,
      y: (Math.min(...ys) + Math.max(...ys) - size) / 2,
      size,
    };
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 512;
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
    ctx.fillStyle = "black";
    ctx.fillRect(0, 0, 512, 512);
    ctx.drawImage(
      source,
      (-crop.x * 512) / size,
      (-crop.y * 512) / size,
      (width * 512) / size,
      (height * 512) / size,
    );
    const pixels = ctx.getImageData(0, 0, 512, 512).data,
      input = new Float32Array(3 * 512 * 512);
    const mean = [0.485, 0.456, 0.406],
      std = [0.229, 0.224, 0.225];
    for (let i = 0; i < 512 * 512; i++)
      for (let c = 0; c < 3; c++)
        input[c * 512 * 512 + i] = (pixels[i * 4 + c] / 255 - mean[c]) / std[c];
    const id = ++requestIdRef.current;
    pendingRef.current = { id, frame: structuredClone(frame), crop };
    detectedRef.current = null;
    setDetecting(true);
    setRecognitionStatus("눈썹 인식 중…");
    workerRef.current.postMessage({ type: "detect", input, id } satisfies BrowRequest, [
      input.buffer,
    ]);
  };

  const toggleFreeze = () => {
    if (!frozen) {
      const video = videoRef.current;
      if (!video?.videoWidth) return;
      const snapshot = document.createElement("canvas");
      snapshot.width = video.videoWidth;
      snapshot.height = video.videoHeight;
      snapshot.getContext("2d")!.drawImage(video, 0, 0);
      frozenVideo.current = snapshot;
      freezeRef.current = true;
      setFrozen(true);
    } else {
      freezeRef.current = false;
      frameRef.current = liveRef.current;
      setFrozen(false);
    }
  };
  return (
    <div className="flex flex-1 flex-col gap-3">
      <div className="flex flex-wrap gap-4">
        <label>
          부위{" "}
          <select value={part} onChange={(e) => setPart(e.target.value)}>
            <option value="blush">블러셔</option>
            <option value="brow">눈썹</option>
          </select>
        </label>
        <label>
          표시{" "}
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="current">변경 전</option>
            <option value="candidate">적용된 기본값</option>
            <option value="both">좌우 비교</option>
          </select>
        </label>
        {live && part === "brow" && (
          <>
            <label>
              <input
                type="checkbox"
                checked={recognition}
                onChange={(e) => {
                  setRecognition(e.target.checked);
                  setModelReady(false);
                  setDetecting(false);
                  setRecognitionStatus(
                    e.target.checked ? "눈썹 모델 로딩 중…" : "꺼짐 · 적용된 기본 가이드",
                  );
                  if (e.target.checked) setMode("candidate");
                }}
              />{" "}
              실제 눈썹 인식 (실험)
            </label>
            {recognition && (
              <>
                <button disabled={!modelReady || detecting || !ready} onClick={detectBrows}>
                  다시 인식
                </button>
                <label>
                  <input
                    type="checkbox"
                    checked={showBoundary}
                    onChange={(e) => setShowBoundary(e.target.checked)}
                  />{" "}
                  검출 경계 표시
                </label>
                <span role="status">{recognitionStatus}</span>
                <p>
                  사진은 서버로 전송하지 않습니다. 정면에서 한 번 인식한 뒤 얼굴 움직임을
                  따라갑니다. 조명·위치가 달라지면 다시 인식해 주세요.
                </p>
              </>
            )}
          </>
        )}
        {!live && (
          <>
            <label>
              얼굴{" "}
              <select value={face} disabled={!!sequence} onChange={(e) => setFace(e.target.value)}>
                {FACES.map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </select>
            </label>
            {Object.keys(SEQUENCES).map((s) => (
              <button key={s} disabled={!!sequence} onClick={() => setSequence(s)}>
                {s} 재생
              </button>
            ))}
          </>
        )}
        {live && (
          <>
            <span>{status}</span>
            <button onClick={toggleFreeze}>{frozen ? "재개" : "화면 고정"}</button>
            {error && <button onClick={() => void start()}>카메라 다시 시도</button>}
          </>
        )}
      </div>
      <p role="status">
        {message ||
          error?.message ||
          (!ready
            ? "가이드 로딩 중…"
            : "같은 크기 전환으로 가독성을 비교하세요. 화면 고정 후에도 변경 전·적용된 기본값을 전환할 수 있습니다.")}
      </p>
      <div
        className={`relative min-h-[480px] flex-1 ${mode === "both" ? "grid grid-cols-2 gap-2" : ""}`}
      >
        {["변경 전", "적용된 기본값"].map((label, i) => (
          <div
            key={label}
            className={
              mode === "both"
                ? "relative min-h-[480px] bg-black"
                : `absolute inset-0 bg-black ${mode === (i === 0 ? "current" : "candidate") ? "z-10" : "pointer-events-none opacity-0"}`
            }
          >
            <canvas
              ref={(c) => {
                backgrounds.current[i] = c;
              }}
              className="absolute inset-0 h-full w-full"
            />
            <canvas
              ref={(c) => {
                canvases.current[i] = c;
              }}
              className="absolute inset-0 h-full w-full"
            />
            <span className="absolute top-2 left-2 text-white">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
