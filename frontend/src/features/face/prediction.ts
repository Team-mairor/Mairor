import { LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER } from "./regions";
import { FRAME_STALE_MS } from "./tracking-rules";
import type { FaceFrame, Point } from "./types";

export interface PredictionOptions {
  strength: number;
  maxMs: number;
  maxDistance: number;
}
export const DEFAULT_PREDICTION: PredictionOptions = {
  strength: 0.6,
  maxMs: 80,
  maxDistance: 0.15,
};

/** 그리기용 전체 얼굴 이동만 예측한다. 관측 결과와 표시 판정은 바꾸지 않는다. */
export class FacePredictor {
  private previous: FaceFrame | null = null;
  private current: FaceFrame | null = null;
  private velocity = { x: 0, y: 0, scale: 0, roll: 0 };

  reset() {
    this.previous = this.current = null;
    this.velocity = { x: 0, y: 0, scale: 0, roll: 0 };
  }

  sample(frame: FaceFrame | null) {
    if (!frame || frame.trackingState === "lost") {
      this.reset();
      return;
    }
    if (this.current === frame) return;
    const previous = this.current;
    this.current = frame;
    this.previous = previous;
    this.velocity = { x: 0, y: 0, scale: 0, roll: 0 };
    if (!previous || frame.trackingState === "hold" || previous.trackingState === "hold") return;
    const dt = frame.timestamp - previous.timestamp;
    if (
      dt <= 0 ||
      dt > FRAME_STALE_MS ||
      previous.imageSize.width !== frame.imageSize.width ||
      previous.imageSize.height !== frame.imageSize.height
    )
      return;
    const a = previous.landmarks[1],
      b = frame.landmarks[1];
    if (!a || !b || !(frame.iod > 0) || !(previous.iod > 0)) return;
    const x = (b.x - a.x) * frame.imageSize.width;
    const y = (b.y - a.y) * frame.imageSize.height;
    if (Math.hypot(x, y) > frame.iod * 0.5 || Math.abs(Math.log(frame.iod / previous.iod)) > 0.2)
      return;
    this.velocity = {
      x: x / dt,
      y: y / dt,
      scale: Math.log(frame.iod / previous.iod) / dt,
      roll: angleDelta(frameAngle(frame), frameAngle(previous)) / dt,
    };
  }

  predict(now: number, options: PredictionOptions = DEFAULT_PREDICTION): FaceFrame | null {
    const frame = this.current;
    if (!frame || now - (frame.detectedAt ?? frame.timestamp) > FRAME_STALE_MS) return null;
    if (!this.previous || frame.trackingState === "hold" || options.strength <= 0) return frame;
    const age = Math.max(0, now - frame.timestamp);
    // 오래된 속도로 계속 미끄러지지 않도록 예측 구간 이후에는 보정을 줄인다.
    const decay = Math.max(
      0,
      1 - Math.max(0, age - options.maxMs) / (FRAME_STALE_MS - options.maxMs),
    );
    const horizon = Math.min(age, options.maxMs) * Math.min(1, options.strength) * decay;
    const limit = frame.iod * options.maxDistance;
    let dx = this.velocity.x * horizon,
      dy = this.velocity.y * horizon;
    const length = Math.hypot(dx, dy);
    if (length > limit) {
      dx *= limit / length;
      dy *= limit / length;
    }
    const scale = Math.exp(Math.max(-0.04, Math.min(0.04, this.velocity.scale * horizon)));
    const roll = Math.max(-0.04, Math.min(0.04, this.velocity.roll * horizon));
    const origin = frame.landmarks[1];
    if (!origin || !Number.isFinite(dx + dy + scale + roll)) return frame;
    const cos = Math.cos(roll),
      sin = Math.sin(roll);
    const transform = (p: Point): Point => {
      const x = (p.x - origin.x) * frame.imageSize.width;
      const y = (p.y - origin.y) * frame.imageSize.height;
      return {
        ...p,
        x: origin.x + ((x * cos - y * sin) * scale + dx) / frame.imageSize.width,
        y: origin.y + ((x * sin + y * cos) * scale + dy) / frame.imageSize.height,
      };
    };
    return { ...frame, landmarks: frame.landmarks.map(transform), iod: frame.iod * scale };
  }
}

function frameAngle(frame: FaceFrame) {
  const left = frame.landmarks[LEFT_IRIS_CENTER];
  const right = frame.landmarks[RIGHT_IRIS_CENTER];
  if (!left || !right) return 0;
  return Math.atan2(
    (left.y - right.y) * frame.imageSize.height,
    (left.x - right.x) * frame.imageSize.width,
  );
}

function angleDelta(current: number, previous: number) {
  return Math.atan2(Math.sin(current - previous), Math.cos(current - previous));
}
