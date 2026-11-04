import type {
  Detection,
  FaceDetector,
  FaceLandmarker,
  FaceLandmarkerResult,
  NormalizedLandmark,
} from "@mediapipe/tasks-vision";

import {
  computeRegion,
  eyeStateFromBlendshape,
  interocularDistance,
  poseFromMatrix,
  regionVisibility,
} from "./geometry";
import { createFaceDetector, createFaceLandmarker } from "./landmarker";
import { REGION_NAMES } from "./regions";
import { LandmarkSmoother, type SmoothingOptions } from "./smoothing";
import { DEFAULT_MAX_YAW, KEY_REGIONS, MIN_KEY_REGIONS_IN_VIEW } from "./tracking-rules";
import type {
  FaceFrame,
  NormalizedRect,
  Point,
  Pose,
  RegionInfo,
  RegionName,
  RegionVisibility,
  TrackingState,
} from "./types";
import { MIN_IN_FRAME_RATIO, RECOVER_IN_FRAME_MARGIN } from "./visibility";

export type CloseUpMode = "auto" | "on" | "off";

export interface TrackerOptions {
  /** 얼굴을 놓친 뒤 마지막 결과를 유지하는 시간(ms) */
  holdMs: number;
  /** 이 각도(라디안)를 넘게 돌리면 반대쪽 부위를 보이지 않는 것으로 본다 */
  maxYaw: number;
  /** 핵심 부위는 화면 안 비율이 이 값 이상이어야 보이는 것으로 친다 */
  minInFrameRatio: number;
  /** 화면에 실제로 보이는 원본 프레임 영역. null이면 프레임 전체 */
  visibleRect: NormalizedRect | null;
  /** 이 eyeBlink 점수 이상이면 눈을 완전히 감은 것으로 본다 */
  closedBlink: number;
  blinkThreshold: number;
  /** 근접 모드: 프레임을 축소해 여백을 두고 넣어, 얼굴이 화면을 넘칠 때도 추적을 유지한다 */
  closeUp: CloseUpMode;
  /** 가장 많이 축소할 때의 배율 */
  closeUpMinScale: number;
  /** auto일 때 IOD / 화면 너비가 이 값을 넘지 않도록 축소한다 */
  closeUpIodRatio: number;
  /** 이 배율보다 많이 축소하면 정확도가 낮아 degraded로 본다 */
  reliableMinScale: number;
  /** null이면 끈다 */
  smoothing: SmoothingOptions | null;
}

/**
 * 추적 한 프레임의 구간별 시간 (ms, 최근 값 위주 평균). 저사양 기기에서 어느 구간이 느린지 찾는 데 쓴다.
 * 한 프레임 = input + detect + frame + largest(돌 때만) + listeners, 그 사이 다음 프레임을 기다린 시간이 idle
 */
export interface TrackerTiming {
  /** 근접 축소·가림용 입력 캔버스 그리기 (영상을 바로 넘기면 0에 가깝다) */
  input: number;
  /** 얼굴 랜드마크 추론 (detectForVideo) */
  detect: number;
  /** 결과를 FaceFrame으로 바꾸기 (떨림 보정·부위 계산) */
  frame: number;
  /** 가장 큰 얼굴 검출기. LARGEST_CHECK_MS마다 돌 때만 잰다 */
  largest: number;
  /** 화면 쪽 처리 (화장 그리기·피부 분할 등 onFrame) */
  listeners: number;
  /** 이전 프레임 처리가 끝나고 이번 프레임이 시작되기까지 */
  idle: number;
}

const TIMING_LABELS: Record<keyof TrackerTiming, string> = {
  input: "입력",
  detect: "검출",
  frame: "변환",
  largest: "큰 얼굴",
  listeners: "화면",
  idle: "대기",
};

/** 확인 화면 표시용 한 줄 (예: "입력 0.4 · 검출 231.0 · …" ms) */
export function formatTiming(timing: TrackerTiming): string {
  return (Object.keys(TIMING_LABELS) as (keyof TrackerTiming)[])
    .map((key) => `${TIMING_LABELS[key]} ${timing[key].toFixed(1)}`)
    .join(" · ");
}

export interface TrackerStats {
  fps: number;
  timing: TrackerTiming;
  /** 입력 축소 배율 (1이면 근접 모드 꺼짐) */
  inputScale: number;
  /** eyeBlink 원본 점수 (조정용) */
  blink: { left: number; right: number };
}

// beta가 작으면 빠르게 움직일 때 늦게 따라오고, minCutoff가 크면 가만히 있을 때 떨린다.
export const DEFAULT_SMOOTHING: SmoothingOptions = { minCutoff: 0.5, beta: 0.1, dCutoff: 1 };

const DEFAULT_OPTIONS: TrackerOptions = {
  holdMs: 500,
  maxYaw: DEFAULT_MAX_YAW,
  minInFrameRatio: MIN_IN_FRAME_RATIO,
  visibleRect: null,
  closedBlink: 0.5,
  blinkThreshold: 0.4,
  closeUp: "auto",
  // 얼굴이 화면을 크게 넘칠 만큼 다가가도 잡히도록 넉넉히 줄인다.
  closeUpMinScale: 0.3,
  closeUpIodRatio: 0.22,
  // 480px 폭에서 최대로 줄이면 얼굴이 약 144px로 랜드마크 모델 입력(192px)보다 작아지지만,
  // 갤럭시탭 S6 Lite에서 이 거리까지 부위 위치가 맞는 것을 확인해 축소 배율로는 degraded로 보지 않는다.
  reliableMinScale: 0,
  smoothing: DEFAULT_SMOOTHING,
};

// 구간별 시간 평균에서 새 값의 비중. 4 FPS에서도 1~2초면 바뀐 값이 드러난다.
const TIMING_WEIGHT = 0.3;
// 기준값 경계에서 상태가 프레임마다 바뀌지 않도록, degraded에서 돌아올 때는 이만큼 더 넘어야 한다.
const RECOVER_SCALE_MARGIN = 0.05;
// 근접 배율이 1 근처에서 오가며 여백이 흔들리지 않도록 1로 붙이고 떼는 기준을 다르게 둔다.
const SNAP_TO_FULL = 0.97;
const LEAVE_FULL = 0.9;
// 얼굴을 못 찾는 동안 원래 크기와 최대 축소를 이 프레임 수마다 번갈아 시도한다.
const SEARCH_SWITCH_FRAMES = 10;
// 화면이 보이는데 이 시간(ms) 동안 프레임이 오지 않으면 영상이 멈춘 것으로 보고 다시 재생한다.
const STALL_MS = 2000;
// 다시 재생해도 이만큼 연속으로 멈춰 있으면 오류로 알린다.
const MAX_STALL_RETRIES = 3;
// 추적 중인 얼굴이 가장 큰 얼굴인지 이 간격마다 확인한다. 한 번에 갤럭시탭 S6 Lite에서 35~55ms라
// 사람이 바뀌는 드문 경우를 위해 자주 돌리지 않는다.
const LARGEST_CHECK_MS = 1500;
// 얼굴을 놓쳤다가 다시 잡은 직후에는 뒤 사람을 잡았을 수 있어 잠시 자주 확인한다.
const REFOUND_MS = 3000;
const REFOUND_CHECK_MS = 500;
// 가장 큰 얼굴 주변만 남길 때, 다시 잡는 사이 얼굴이 조금 움직여도 영역 안에 남도록 넓힌다.
// 너무 넓히면 옆 얼굴까지 남아 다시 잡지 못한다.
const LOCK_MARGIN = 0.2;
// 이 시간 안에 가장 큰 얼굴을 다시 잡지 못하면 가리기를 그만둔다.
const LOCK_TIMEOUT_MS = 1000;
// 손 등에 가려 지금 얼굴이 작게 잡히는 사이 뒤 사람으로 넘어가지 않도록, 다른 얼굴이 이만큼 더 크고
// 연달아 이 횟수만큼 확인됐을 때만 바꾼다.
const SWITCH_AREA_RATIO = 1.5;
const SWITCH_CONFIRMS = 2;

/** 다시 재생해도 카메라 영상이 계속 멈춰 있을 때 onError로 넘기는 오류. 검출 실패와 안내를 구분한다. */
export class VideoStalledError extends Error {
  constructor() {
    super("카메라 영상이 멈췄습니다");
    this.name = "VideoStalledError";
  }
}

export class FaceTracker {
  private landmarker: FaceLandmarker | null = null;
  private detector: FaceDetector | null = null;
  private lastCheckAt = -Infinity;
  /** 얼굴을 처음 또는 놓쳤다가 다시 잡은 시각 */
  private foundAt = -Infinity;
  /** 다른 얼굴을 따라가고 있을 때, 가장 큰 얼굴을 다시 잡을 때까지 이 영역만 입력에 남긴다. */
  private lockBox: Box | null = null;
  /** 다시 잡으려는 가장 큰 얼굴 박스 (넓히기 전) */
  private lockTarget: Box | null = null;
  private lockedAt = 0;
  private switchConfirms = 0;
  private running = false;
  private disposed = false;
  private lastFrame: FaceFrame | null = null;
  private lastState: TrackingState | null = null;
  private lastSeenAt = 0;
  private lastTimestamp = -1;
  private frameTimes: number[] = [];
  private lastTickEnd: number | null = null;
  /** 시간을 잰 프레임 수. 첫 프레임은 모델 초기화가 섞여 수 초씩 걸리므로 평균에서 뺀다 */
  private timedTicks = 0;
  private inputScale = 1;
  private searchFrames = 0;
  private frameHandle: { kind: "video" | "animation"; id: number } | null = null;
  private starting: Promise<void> | null = null;
  private lastTickAt = 0;
  private stallRetries = 0;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private smoother: LandmarkSmoother | null = null;
  private options: TrackerOptions;

  stats: TrackerStats = {
    fps: 0,
    timing: { input: 0, detect: 0, frame: 0, largest: 0, listeners: 0, idle: 0 },
    inputScale: 1,
    blink: { left: 0, right: 0 },
  };

  constructor(
    private readonly video: HTMLVideoElement,
    private readonly onFrame: (frame: FaceFrame | null, stats: TrackerStats) => void,
    options: Partial<TrackerOptions> = {},
    /** 추적 도중 검출이 실패해 멈췄을 때 호출된다. */
    private readonly onError?: (error: unknown) => void,
  ) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.resetSmoother();
  }

  start(): Promise<void> {
    // 동시에 두 번 불러도 모델과 루프는 하나만 만든다.
    this.starting ??= this.doStart().finally(() => {
      this.starting = null;
    });
    return this.starting;
  }

  private async doStart() {
    // 가장 큰 얼굴 확인은 부가 기능이라, 검출기를 불러오지 못해도 추적은 계속한다.
    const detecting = this.detector
      ? Promise.resolve(this.detector)
      : createFaceDetector().catch((e) => {
          console.warn("얼굴 검출기를 불러오지 못해 가장 큰 얼굴 확인 없이 추적합니다", e);
          return null;
        });
    let landmarker: FaceLandmarker;
    try {
      landmarker = this.landmarker ?? (await createFaceLandmarker());
    } catch (e) {
      if (!this.detector) (await detecting)?.close();
      throw e;
    }
    const detector = await detecting;
    // 모델을 불러오는 동안 dispose되었으면 시작하지 않는다.
    if (this.disposed) {
      landmarker.close();
      detector?.close();
      return;
    }
    this.landmarker = landmarker;
    this.detector = detector;
    if (this.running) return;
    this.running = true;
    this.lastTickAt = performance.now();
    this.stallRetries = 0;
    document.addEventListener("visibilitychange", this.onVisibilityChange);
    this.watchdog = setInterval(this.checkStall, STALL_MS / 2);
    this.scheduleNext();
  }

  // 태블릿 화면이 꺼지거나 백그라운드로 가면 브라우저가 영상을 멈추고, 돌아와도 다시 재생하지 않는다.
  private readonly onVisibilityChange = () => {
    if (document.visibilityState !== "visible" || !this.running) return;
    // 숨어 있던 동안은 멈춘 게 아니므로, 다시 보인 시점부터 재고 재시도 횟수도 새로 센다.
    this.lastTickAt = performance.now();
    this.stallRetries = 0;
    this.resume();
  };

  private readonly checkStall = () => {
    if (!this.running || document.visibilityState !== "visible") return;
    if (performance.now() - this.lastTickAt < STALL_MS) return;
    if (++this.stallRetries > MAX_STALL_RETRIES) {
      this.stop();
      this.onError?.(new VideoStalledError());
      return;
    }
    this.lastTickAt = performance.now();
    this.resume();
  };

  /** 멈춘 영상을 다시 재생하고 프레임 콜백을 새로 예약한다. */
  private resume() {
    if (this.video.paused) {
      this.video.play().catch((e) => console.warn("카메라 영상을 다시 재생하지 못했습니다", e));
    }
    this.cancelFrame();
    // 멈춰 있던 동안은 대기 시간에 넣지 않는다.
    this.lastTickEnd = null;
    this.scheduleNext();
  }

  private cancelFrame() {
    const handle = this.frameHandle;
    if (handle?.kind === "video") this.video.cancelVideoFrameCallback(handle.id);
    else if (handle) cancelAnimationFrame(handle.id);
    this.frameHandle = null;
  }

  stop() {
    this.running = false;
    document.removeEventListener("visibilitychange", this.onVisibilityChange);
    if (this.watchdog) clearInterval(this.watchdog);
    this.watchdog = null;
    // 이미 예약된 콜백이 남아 있으면 다시 start했을 때 루프가 두 개 돈다.
    this.cancelFrame();
    this.lastTickEnd = null;
  }

  /** 카메라·해상도를 바꿨을 때처럼 이전 프레임 기준 상태를 버린다. */
  reset() {
    this.smoother?.reset();
    this.lastFrame = null;
    this.lastState = null;
    this.searchFrames = 0;
    // 이전 카메라 기준 영역으로 입력을 가리지 않도록 가장 큰 얼굴 확인도 처음부터 한다.
    this.lockBox = null;
    this.lockTarget = null;
    this.switchConfirms = 0;
  }

  dispose() {
    this.disposed = true;
    this.stop();
    this.landmarker?.close();
    this.landmarker = null;
    this.detector?.close();
    this.detector = null;
  }

  setOptions(options: Partial<TrackerOptions>) {
    const smoothingChanged =
      "smoothing" in options &&
      JSON.stringify(options.smoothing) !== JSON.stringify(this.options.smoothing);
    this.options = { ...this.options, ...options };
    if (smoothingChanged) this.resetSmoother();
  }

  private resetSmoother() {
    this.smoother = this.options.smoothing ? new LandmarkSmoother(this.options.smoothing) : null;
  }

  private scheduleNext() {
    if (!this.running) return;
    if ("requestVideoFrameCallback" in this.video) {
      this.frameHandle = {
        kind: "video",
        id: this.video.requestVideoFrameCallback(() => this.tick()),
      };
    } else {
      this.frameHandle = { kind: "animation", id: requestAnimationFrame(() => this.tick()) };
    }
  }

  private tick() {
    if (!this.running || !this.landmarker) return;
    this.lastTickAt = performance.now();
    this.stallRetries = 0;

    const video = this.video;
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && video.videoWidth > 0) {
      // detectForVideo는 단조 증가하는 타임스탬프가 필요하다.
      const now = Math.max(performance.now(), this.lastTimestamp + 1);
      this.lastTimestamp = now;

      const lockBox = this.lockBox;
      let frame: FaceFrame | null;
      let input: HTMLVideoElement | HTMLCanvasElement;
      let scale: number;
      if (this.lastTickEnd !== null) this.recordTiming("idle", now - this.lastTickEnd);
      try {
        this.updateInputScale();
        scale = this.inputScale;
        input = scale < 1 || lockBox ? this.drawInput(scale, lockBox) : video;
        const inputEnd = performance.now();
        this.recordTiming("input", inputEnd - now);

        const result = this.landmarker.detectForVideo(input, now);
        const detectEnd = performance.now();
        this.recordTiming("detect", detectEnd - inputEnd);
        this.stats.inputScale = scale;
        this.updateFps(now);
        frame = this.toFrame(result, now, scale);
        this.recordTiming("frame", performance.now() - detectEnd);
      } catch (e) {
        // GPU 컨텍스트 손실처럼 대개 다시 해도 실패하므로 멈추고 알린다.
        this.stop();
        this.onError?.(e);
        return;
      }

      if (lockBox) this.updateLock(frame, now);
      else this.checkLargestFace(input, frame, now, scale);

      // 화면 쪽 처리에서 난 예외 때문에 추적이 멈추지 않게 한다.
      const listenersStart = performance.now();
      try {
        this.onFrame(frame, this.stats);
      } catch (e) {
        console.error(e);
      }
      this.lastTickEnd = performance.now();
      this.recordTiming("listeners", this.lastTickEnd - listenersStart);
      this.timedTicks++;
    }

    this.scheduleNext();
  }

  private recordTiming(key: keyof TrackerTiming, ms: number) {
    if (this.timedTicks === 0) return;
    const timing = this.stats.timing;
    // 처음 값은 그대로 쓰고, 이후에는 최근 값 위주로 평균한다.
    timing[key] = timing[key] === 0 ? ms : timing[key] + (ms - timing[key]) * TIMING_WEIGHT;
  }

  // 얼굴이 너무 크게 잡히면 필요한 만큼만 축소한다. 축소할수록 얼굴 해상도가 떨어져 정확도도 낮아진다.
  private updateInputScale() {
    const { closeUp, closeUpIodRatio, closeUpMinScale } = this.options;
    if (closeUp !== "auto") {
      this.inputScale = closeUp === "on" ? closeUpMinScale : 1;
      return;
    }
    const frame = this.lastFrame;
    // 얼굴을 못 찾았으면 화면을 넘칠 만큼 가까워서일 수도, 멀어서일 수도 있어
    // 원래 크기와 최대 축소를 번갈아 시도한다. 처음 시작할 때도 같다.
    if (!frame || this.lastState === "hold" || this.lastState === "lost") {
      const phase = Math.floor(this.searchFrames++ / SEARCH_SWITCH_FRAMES) % 2;
      this.inputScale = phase === 0 ? 1 : closeUpMinScale;
      return;
    }
    this.searchFrames = 0;
    const ratio = frame.iod / frame.imageSize.width;
    const target = Math.max(closeUpMinScale, Math.min(1, closeUpIodRatio / ratio));
    const snap = this.inputScale === 1 ? target > LEAVE_FULL : target > SNAP_TO_FULL;
    this.inputScale = snap ? 1 : this.inputScale * 0.7 + target * 0.3;
  }

  // 랜드마크 추적은 얼굴 하나만 따라가서, 가림 뒤에 다른 얼굴로 넘어가면 그대로 남는다.
  // 검출기로 가장 큰 얼굴을 찾아 지금 얼굴과 다르면 그 주변만 남겨 다시 잡게 한다.
  private checkLargestFace(
    input: HTMLVideoElement | HTMLCanvasElement,
    frame: FaceFrame | null,
    now: number,
    scale: number,
  ) {
    const interval = now - this.foundAt < REFOUND_MS ? REFOUND_CHECK_MS : LARGEST_CHECK_MS;
    if (!this.detector || now - this.lastCheckAt < interval) return;
    this.lastCheckAt = now;
    // 잠깐 가려진 동안은 바꾸지 않는다.
    if (frame?.trackingState === "hold") {
      this.switchConfirms = 0;
      return;
    }

    let detections: Detection[];
    const start = performance.now();
    try {
      ({ detections } = this.detector.detectForVideo(input, now));
      this.recordTiming("largest", performance.now() - start);
    } catch (e) {
      // 부가 기능이라 실패하면 끄고 추적은 계속한다.
      console.warn("얼굴 검출기가 실패해 가장 큰 얼굴 확인을 끕니다", e);
      this.detector.close();
      this.detector = null;
      return;
    }

    const { videoWidth: w, videoHeight: h } = this.video;
    const offset = (1 - scale) / 2;
    const boxes: Box[] = [];
    for (const { boundingBox: b } of detections) {
      if (!b) continue;
      boxes.push({
        minX: (b.originX / w - offset) / scale,
        minY: (b.originY / h - offset) / scale,
        maxX: ((b.originX + b.width) / w - offset) / scale,
        maxY: ((b.originY + b.height) / h - offset) / scale,
      });
    }
    let largest: Box | null = null;
    for (const box of boxes) if (!largest || boxArea(box) > boxArea(largest)) largest = box;
    if (!largest) return;

    if (isTracking(frame)) {
      const center = boxCenter(boundingBox(frame.landmarks));
      // 크기는 같은 검출기 박스끼리 비교한다. 랜드마크 박스는 검출기 박스와 범위가 달라서다.
      const current =
        boxes.find((box) => containsPoint(box, center)) ?? boundingBox(frame.landmarks);
      const bigger =
        !containsPoint(largest, center) && boxArea(largest) >= boxArea(current) * SWITCH_AREA_RATIO;
      this.switchConfirms = bigger ? this.switchConfirms + 1 : 0;
      if (this.switchConfirms < SWITCH_CONFIRMS) return;
    }
    this.switchConfirms = 0;
    this.lockBox = expandBox(largest, LOCK_MARGIN);
    this.lockTarget = largest;
    this.lockedAt = now;
  }

  private updateLock(frame: FaceFrame | null, now: number) {
    const target = this.lockTarget;
    const caught =
      !!target &&
      isTracking(frame) &&
      containsPoint(target, boxCenter(boundingBox(frame.landmarks)));
    if (caught || now - this.lockedAt > LOCK_TIMEOUT_MS) this.lockBox = null;
  }

  private drawInput(scale: number, mask: Box | null) {
    const { videoWidth: w, videoHeight: h } = this.video;
    this.canvas ??= document.createElement("canvas");
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    const ctx = this.canvas.getContext("2d")!;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, w, h);
    const x = (w * (1 - scale)) / 2;
    const y = (h * (1 - scale)) / 2;
    ctx.save();
    if (mask) {
      ctx.beginPath();
      ctx.rect(
        x + mask.minX * w * scale,
        y + mask.minY * h * scale,
        (mask.maxX - mask.minX) * w * scale,
        (mask.maxY - mask.minY) * h * scale,
      );
      ctx.clip();
    }
    ctx.drawImage(this.video, x, y, w * scale, h * scale);
    ctx.restore();
    return this.canvas;
  }

  private updateFps(now: number) {
    this.frameTimes.push(now);
    while (this.frameTimes.length > 0 && now - this.frameTimes[0] > 1000) {
      this.frameTimes.shift();
    }
    this.stats.fps = this.frameTimes.length;
  }

  private toFrame(
    result: FaceLandmarkerResult,
    timestamp: number,
    scale: number,
  ): FaceFrame | null {
    const raw = result.faceLandmarks[0];

    if (!raw) {
      if (!this.lastFrame) return null;
      const state: TrackingState =
        timestamp - this.lastSeenAt <= this.options.holdMs ? "hold" : "lost";
      if (state === "lost") this.smoother?.reset();
      this.lastState = state;
      return { ...this.lastFrame, timestamp, trackingState: state };
    }

    const imageSize = { width: this.video.videoWidth, height: this.video.videoHeight };
    // 카메라·해상도가 바뀌면 이전 픽셀 좌표가 남지 않도록 떨림 보정을 새로 시작한다.
    const prevSize = this.lastFrame?.imageSize;
    if (prevSize && (prevSize.width !== imageSize.width || prevSize.height !== imageSize.height)) {
      this.smoother?.reset();
    }
    const unpadded = scale < 1 ? unpad(raw, scale) : raw;
    const landmarks = this.smoother
      ? this.smoother.apply(unpadded, imageSize, timestamp)
      : unpadded;
    const iod = interocularDistance(landmarks, imageSize);

    const matrix = result.facialTransformationMatrixes[0];
    const pose: Pose = matrix ? poseFromMatrix(matrix.data) : { yaw: 0, pitch: 0, roll: 0 };

    const blend = new Map(
      (result.faceBlendshapes[0]?.categories ?? []).map((c) => [c.categoryName, c.score]),
    );
    const { closedBlink, blinkThreshold, maxYaw, minInFrameRatio, reliableMinScale } = this.options;
    const blinkLeft = blend.get("eyeBlinkLeft") ?? 0;
    const blinkRight = blend.get("eyeBlinkRight") ?? 0;
    this.stats.blink = { left: blinkLeft, right: blinkRight };

    const regions = {} as Record<RegionName, RegionInfo>;
    const visibility = {} as Record<RegionName, RegionVisibility>;
    for (const name of REGION_NAMES) {
      regions[name] = computeRegion(name, landmarks, imageSize, iod);
      visibility[name] = regionVisibility(
        name,
        landmarks,
        pose,
        maxYaw,
        this.options.visibleRect ?? undefined,
      );
    }

    // 이미 degraded면 기준을 조금 더 넘어야 tracking으로 돌아온다.
    const wasDegraded = this.lastState === "degraded";
    const scaleLimit = reliableMinScale + (wasDegraded ? RECOVER_SCALE_MARGIN : 0);
    const inFrameLimit = minInFrameRatio + (wasDegraded ? RECOVER_IN_FRAME_MARGIN : 0);
    const inView = KEY_REGIONS.filter(
      (name) => visibility[name].inFrameRatio >= inFrameLimit && visibility[name].facing,
    ).length;
    const degraded = scale < scaleLimit || inView < MIN_KEY_REGIONS_IN_VIEW;

    const frame: FaceFrame = {
      version: "0.2",
      meshVersion: "v1",
      timestamp,
      imageSize,
      trackingState: degraded ? "degraded" : "tracking",
      landmarks,
      iod,
      pose,
      eyes: {
        left: eyeStateFromBlendshape(blinkLeft, closedBlink, blinkThreshold),
        right: eyeStateFromBlendshape(blinkRight, closedBlink, blinkThreshold),
      },
      regions,
      regionVisibility: visibility,
    };

    if (this.lastState === null || this.lastState === "lost") this.foundAt = timestamp;
    this.lastFrame = frame;
    this.lastState = frame.trackingState;
    this.lastSeenAt = timestamp;
    return frame;
  }
}

interface Box {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

function isTracking(frame: FaceFrame | null): frame is FaceFrame {
  return !!frame && frame.trackingState !== "hold" && frame.trackingState !== "lost";
}

function boundingBox(points: Point[]): Box {
  const box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
  for (const p of points) {
    box.minX = Math.min(box.minX, p.x);
    box.minY = Math.min(box.minY, p.y);
    box.maxX = Math.max(box.maxX, p.x);
    box.maxY = Math.max(box.maxY, p.y);
  }
  return box;
}

/** 각 변을 박스 크기의 ratio만큼 바깥으로 넓힌다. */
function expandBox(box: Box, ratio: number): Box {
  const dx = (box.maxX - box.minX) * ratio;
  const dy = (box.maxY - box.minY) * ratio;
  return { minX: box.minX - dx, minY: box.minY - dy, maxX: box.maxX + dx, maxY: box.maxY + dy };
}

function boxArea(box: Box) {
  return (box.maxX - box.minX) * (box.maxY - box.minY);
}

function boxCenter(box: Box) {
  return { x: (box.minX + box.maxX) / 2, y: (box.minY + box.maxY) / 2 };
}

function containsPoint(box: Box, p: { x: number; y: number }) {
  return p.x >= box.minX && p.x <= box.maxX && p.y >= box.minY && p.y <= box.maxY;
}

/** 여백을 두고 축소해 넣은 프레임의 좌표를 원본 프레임 좌표로 되돌린다. */
function unpad(landmarks: NormalizedLandmark[], scale: number): Point[] {
  const offset = (1 - scale) / 2;
  return landmarks.map((p) => ({
    x: (p.x - offset) / scale,
    y: (p.y - offset) / scale,
    z: p.z / scale,
  }));
}
