import type { FaceFrame } from "@/features/face";
import { rgbToLab, type Lab } from "@/lib/color";

const FOREHEAD = 151;
const RADIUS_IOD = 0.12;
const WINDOW_MS = 1000;

export type ColorStats = {
  mean: Lab;
  /** 최근 1초 동안 색이 흔들린 정도(ΔE). 가만히 있을 때 작을수록 색 측정이 안정적이다. */
  jitter: number;
};

/** 이마 영역 평균 색(Lab)과 최근 1초 동안의 흔들림(표준편차)을 잰다. */
export class ColorProbe {
  private canvas = document.createElement("canvas");
  private history: { t: number; lab: Lab }[] = [];

  sample(video: HTMLVideoElement, frame: FaceFrame): ColorStats | null {
    const { width, height } = frame.imageSize;
    const p = frame.landmarks[FOREHEAD];
    const r = Math.max(2, Math.round(frame.iod * RADIUS_IOD));
    const x = Math.round(p.x * width) - r;
    const y = Math.round(p.y * height) - r;
    if (x < 0 || y < 0 || x + r * 2 > width || y + r * 2 > height) return null;

    this.canvas.width = r * 2;
    this.canvas.height = r * 2;
    const ctx = this.canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.drawImage(video, x, y, r * 2, r * 2, 0, 0, r * 2, r * 2);
    const { data } = ctx.getImageData(0, 0, r * 2, r * 2);

    let sr = 0;
    let sg = 0;
    let sb = 0;
    const n = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      sr += data[i];
      sg += data[i + 1];
      sb += data[i + 2];
    }
    const lab = rgbToLab(sr / n, sg / n, sb / n);

    const now = frame.timestamp;
    this.history.push({ t: now, lab });
    this.history = this.history.filter((h) => now - h.t <= WINDOW_MS);
    const sd = std(this.history.map((h) => h.lab));
    return { mean: lab, jitter: Math.hypot(sd.l, sd.a, sd.b) };
  }
}

function std(values: Lab[]): Lab {
  const keys = ["l", "a", "b"] as const;
  const out = { l: 0, a: 0, b: 0 };
  for (const k of keys) {
    const mean = values.reduce((s, v) => s + v[k], 0) / values.length;
    out[k] = Math.sqrt(values.reduce((s, v) => s + (v[k] - mean) ** 2, 0) / values.length);
  }
  return out;
}
