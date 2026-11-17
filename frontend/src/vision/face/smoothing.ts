import type { Point } from "./types";

// One Euro 필터: 천천히 움직일 땐 떨림을 많이 줄이고, 빠르게 움직일 땐 지연을 줄인다.
class OneEuro {
  private x: number | null = null;
  private dx = 0;
  private t = 0;

  constructor(
    private minCutoff: number,
    private beta: number,
    private dCutoff: number,
  ) {}

  private static alpha(cutoff: number, dt: number) {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }

  filter(value: number, timestamp: number) {
    if (this.x === null) {
      this.x = value;
      this.t = timestamp;
      return value;
    }
    const dt = Math.max((timestamp - this.t) / 1000, 1e-3);
    this.t = timestamp;

    const aD = OneEuro.alpha(this.dCutoff, dt);
    this.dx = aD * ((value - this.x) / dt) + (1 - aD) * this.dx;

    const cutoff = this.minCutoff + this.beta * Math.abs(this.dx);
    const a = OneEuro.alpha(cutoff, dt);
    this.x = a * value + (1 - a) * this.x;
    return this.x;
  }
}

export interface SmoothingOptions {
  minCutoff: number;
  beta: number;
  dCutoff: number;
}

/** 랜드마크를 픽셀 단위로 필터링한다. */
export class LandmarkSmoother {
  private filters: OneEuro[] = [];

  constructor(private options: SmoothingOptions) {}

  reset() {
    this.filters = [];
  }

  apply(landmarks: Point[], size: { width: number; height: number }, timestamp: number): Point[] {
    const { minCutoff, beta, dCutoff } = this.options;
    if (this.filters.length !== landmarks.length * 2) {
      this.filters = Array.from(
        { length: landmarks.length * 2 },
        () => new OneEuro(minCutoff, beta, dCutoff),
      );
    }
    return landmarks.map((p, i) => ({
      x: this.filters[i * 2].filter(p.x * size.width, timestamp) / size.width,
      y: this.filters[i * 2 + 1].filter(p.y * size.height, timestamp) / size.height,
      z: p.z,
    }));
  }
}
