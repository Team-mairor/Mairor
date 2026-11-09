import type { Detection, FaceLandmarkerResult } from "@mediapipe/tasks-vision";

import {
  createFaceDetector,
  createFaceLandmarker,
  landmarkerInfo,
  landmarkerPreference,
} from "./landmarker";

export interface InferenceResult {
  result: FaceLandmarkerResult;
  detections?: Detection[];
  detectMs: number;
  largestMs: number;
}

export interface FaceInference {
  backend: "worker" | "main";
  detect(
    input: HTMLVideoElement | HTMLCanvasElement,
    timestamp: number,
    checkLargest: boolean,
  ): Promise<InferenceResult>;
  dispose(): void;
}

type WorkerReply =
  | { type: "ready"; delegate: "CPU" | "GPU" }
  | ({ type: "result"; id: number } & InferenceResult)
  | { type: "error"; id?: number; message: string };

/** Worker로 넘길 영상 이미지를 만들지 못했다. Worker 실패가 아니라 그 프레임만 건너뛴다 */
export class FrameCaptureError extends Error {
  constructor(cause: unknown) {
    super("얼굴 추론에 넘길 영상 이미지를 만들지 못했습니다", { cause });
    this.name = "FrameCaptureError";
  }
}

/** worker가 false면 Worker를 쓰지 않고 메인 스레드에서 추론한다. */
export async function createFaceInference({ worker = true } = {}): Promise<FaceInference> {
  if (
    worker &&
    typeof Worker !== "undefined" &&
    typeof createImageBitmap !== "undefined" &&
    typeof OffscreenCanvas !== "undefined"
  ) {
    try {
      return await createWorkerInference();
    } catch (error) {
      console.warn("Worker 추론을 시작하지 못해 메인 스레드로 추적합니다", error);
    }
  }
  const landmarker = await createFaceLandmarker();
  let detector = await createFaceDetector().catch(() => null);
  let disposed = false;
  return {
    backend: "main",
    async detect(input, timestamp, checkLargest) {
      const start = performance.now();
      const result = landmarker.detectForVideo(input, timestamp);
      const detected = performance.now();
      let detections: Detection[] | undefined;
      if (checkLargest && detector) {
        try {
          detections = detector.detectForVideo(input, timestamp).detections;
        } catch {
          detector.close();
          detector = null;
        }
      }
      return {
        result,
        detections,
        detectMs: detected - start,
        largestMs: performance.now() - detected,
      };
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      landmarker.close();
      detector?.close();
    },
  };
}

function createWorkerInference(): Promise<FaceInference> {
  return new Promise((resolve, reject) => {
    const worker = new Worker("/mediapipe/face-worker.js");
    let disposed = false;
    let capturing = false;
    let sequence = 0;
    let pending: {
      id: number;
      resolve: (value: InferenceResult) => void;
      reject: (error: Error) => void;
      timer: ReturnType<typeof setTimeout>;
    } | null = null;
    const timer = setTimeout(() => fail(new Error("얼굴 추론 Worker 준비 시간 초과")), 30000);
    const fail = (error: Error) => {
      if (disposed) return;
      clearTimeout(timer);
      if (pending) {
        clearTimeout(pending.timer);
        pending.reject(error);
        pending = null;
      }
      disposed = true;
      worker.terminate();
      reject(error);
    };
    const engine: FaceInference = {
      backend: "worker",
      async detect(input, timestamp, checkLargest) {
        if (disposed) throw new Error("얼굴 추론 Worker가 종료됐습니다");
        if (pending || capturing) throw new Error("얼굴 추론은 한 번에 하나만 실행할 수 있습니다");
        capturing = true;
        let image: ImageBitmap;
        try {
          image = await createImageBitmap(input);
        } catch (error) {
          throw new FrameCaptureError(error);
        } finally {
          capturing = false;
        }
        if (disposed) {
          image.close();
          throw new Error("얼굴 추론 Worker가 종료됐습니다");
        }
        return new Promise<InferenceResult>((resolveFrame, rejectFrame) => {
          const id = ++sequence;
          pending = {
            id,
            resolve: resolveFrame,
            reject: rejectFrame,
            timer: setTimeout(() => fail(new Error("얼굴 추론 응답 시간 초과")), 10000),
          };
          try {
            worker.postMessage({ type: "detect", id, image, timestamp, checkLargest }, [image]);
          } catch (error) {
            image.close();
            fail(error instanceof Error ? error : new Error(String(error)));
          }
        });
      },
      dispose() {
        fail(new Error("얼굴 추론 Worker가 종료됐습니다"));
      },
    };
    worker.onmessage = ({ data }: MessageEvent<WorkerReply>) => {
      if (disposed) return;
      if (data.type === "ready") {
        clearTimeout(timer);
        landmarkerInfo.delegate = data.delegate;
        landmarkerInfo.gpu = "Worker";
        resolve(engine);
      } else if (data.type === "error") fail(new Error(data.message));
      else if (pending?.id === data.id) {
        clearTimeout(pending.timer);
        pending.resolve(data);
        pending = null;
      }
    };
    worker.onerror = (event) => fail(new Error(event.message || "얼굴 추론 Worker 오류"));
    worker.postMessage({ type: "init", preference: landmarkerPreference() });
  });
}
