import { rgbToLab, type Lab } from "@/lib/color";

type Range = { min: number; max: number; step?: number };

/** 30fps를 지키는 노출 시간(100µs 단위) */
const FRAME_EXPOSURE = 333;
const SETTLE_MS = 700;

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** 영상 전체 평균 색. 자동 노출도 화면 전체를 보고 밝기를 정한다 */
function frameLab(video: HTMLVideoElement, canvas: HTMLCanvasElement): Lab {
  canvas.width = 96;
  canvas.height = 128;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  let r = 0;
  let g = 0;
  let b = 0;
  for (let i = 0; i < data.length; i += 4) {
    r += data[i];
    g += data[i + 1];
    b += data[i + 2];
  }
  const n = data.length / 4;
  return rgbToLab(r / n, g / n, b / n);
}

async function settle(video: HTMLVideoElement, canvas: HTMLCanvasElement) {
  await wait(SETTLE_MS);
  return frameLab(video, canvas);
}

const apply = (track: MediaStreamTrack, c: Record<string, unknown>) =>
  track.applyConstraints({ advanced: [c as MediaTrackConstraintSet] });

/**
 * 자동일 때와 같은 밝기·색으로 수동 고정한다.
 * 이 기기는 자동 중에도 노출·ISO·색온도를 실제와 다르게 알려 줘, 알려 준 값으로 고정하면 화면이 어두워진다
 */
export async function matchLock(
  track: MediaStreamTrack,
  video: HTMLVideoElement,
): Promise<Record<string, string>> {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  const iso = caps.iso as Range | undefined;
  const temp = caps.colorTemperature as Range | undefined;
  const time = caps.exposureTime as Range | undefined;
  const canvas = document.createElement("canvas");
  const result: Record<string, string> = {};

  await apply(track, { exposureMode: "continuous", whiteBalanceMode: "continuous" });
  const target = await settle(video, canvas);

  if (iso && time) {
    const exposureTime = Math.min(time.max, Math.max(time.min, FRAME_EXPOSURE));
    // ISO는 밝기와 대략 로그 비례라 로그 축에서 반씩 좁힌다
    let lo = Math.log(iso.min);
    let hi = Math.log(iso.max);
    let best = { iso: iso.min, diff: Infinity };
    for (let i = 0; i < 7; i++) {
      const value = Math.round(Math.exp((lo + hi) / 2));
      await apply(track, { exposureMode: "manual", exposureTime, iso: value });
      const l = (await settle(video, canvas)).l;
      if (Math.abs(l - target.l) < best.diff) best = { iso: value, diff: Math.abs(l - target.l) };
      if (l < target.l) lo = Math.log(value);
      else hi = Math.log(value);
    }
    await apply(track, { exposureMode: "manual", exposureTime, iso: best.iso });
    result.exposure = `고정 (ISO ${best.iso}, 밝기 차 ${best.diff.toFixed(1)})`;
  } else {
    result.exposure = "ISO 조절 미지원";
  }

  if (temp) {
    let best = { k: temp.min, diff: Infinity };
    for (let k = Math.ceil(temp.min / 500) * 500; k <= temp.max; k += 500) {
      await apply(track, { whiteBalanceMode: "manual", colorTemperature: k });
      const lab = await settle(video, canvas);
      const diff = Math.hypot(lab.a - target.a, lab.b - target.b);
      if (diff < best.diff) best = { k, diff };
    }
    await apply(track, { whiteBalanceMode: "manual", colorTemperature: best.k });
    result.whiteBalance = `고정 (${best.k}K, 색 차 ${best.diff.toFixed(1)})`;
  } else {
    result.whiteBalance = "색온도 조절 미지원";
  }
  return result;
}
