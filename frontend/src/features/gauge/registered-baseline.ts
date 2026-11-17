import type { FaceFrame } from "@/features/face";

import { buildBaseline, type Baseline } from "./baseline";
import { readCells, type Pixels } from "./cells";
import { eyesOpen } from "./frame";
import type { Samplers } from "./use-gauge-baseline";
import { readEyePixels, whiteOfFrames } from "./white";

const FRONT_MAX = 0.1;
const ROLL_MAX = 0.15;
const EYES_OPEN_MIN = 0.7;
const FRAME_COUNT = 15;

export interface RegisteredGaugeBaseline {
  runId: string;
  track: MediaStreamTrack;
  baseline: Baseline;
  white: [number, number, number] | null;
  center: number;
  lock: Record<string, string>;
}

let saved: RegisteredGaugeBaseline | null = null;

export function saveRegisteredGaugeBaseline(value: RegisteredGaugeBaseline) {
  saved = value;
}

export function registeredGaugeBaseline(runId: string, track: MediaStreamTrack | null) {
  return saved?.runId === runId && saved.track === track ? saved : null;
}

export function clearRegisteredGaugeBaseline(runId?: string) {
  if (runId === undefined || saved?.runId === runId) saved = null;
}

export class RegisteredBaselineCollector {
  private grids: ReturnType<typeof readCells>[] = [];
  private eyes: Float32Array[] = [];
  private pitches: number[] = [];
  private lastFrame = -Infinity;

  push(frame: FaceFrame, pixels: Pixels, samplers: Samplers) {
    const at = frame.detectedAt ?? frame.timestamp;
    if (at === this.lastFrame || this.done) return false;
    const { yaw, pitch, roll } = frame.pose;
    if (
      Math.abs(yaw) > FRONT_MAX ||
      Math.abs(pitch) > FRONT_MAX ||
      Math.abs(roll) > ROLL_MAX ||
      eyesOpen(frame) < EYES_OPEN_MIN
    )
      return false;
    this.lastFrame = at;
    this.grids.push(readCells(pixels, frame.landmarks, samplers.cells));
    this.eyes.push(readEyePixels(pixels, frame.landmarks, samplers.eyes));
    this.pitches.push(pitch);
    return true;
  }

  reset() {
    this.grids = [];
    this.eyes = [];
    this.pitches = [];
    this.lastFrame = -Infinity;
  }

  get count() {
    return this.grids.length;
  }

  get done() {
    return this.count >= FRAME_COUNT;
  }

  build() {
    if (!this.done) return null;
    const pitches = [...this.pitches].sort((a, b) => a - b);
    return {
      baseline: buildBaseline(this.grids),
      white: whiteOfFrames(this.eyes),
      center: pitches[Math.floor(pitches.length / 2)],
    };
  }
}
