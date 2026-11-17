export const RESOLUTIONS = [
  { label: "640×480", width: 640, height: 480 },
  { label: "1280×720", width: 1280, height: 720 },
  { label: "1920×1080", width: 1920, height: 1080 },
] as const;

export async function listCameras(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "videoinput");
}

export type CameraErrorKind =
  | "insecure"
  | "unsupported"
  | "permission-denied"
  | "blocked"
  | "not-found"
  | "in-use"
  | "disconnected"
  | "tracker-failed"
  | "unknown";

export class CameraError extends Error {
  constructor(
    readonly kind: CameraErrorKind,
    message: string,
  ) {
    super(message);
  }
}

function toCameraError(e: unknown): CameraError {
  if (e instanceof CameraError) return e;
  // 브라우저에 따라 DOMException이 아닌 오류 객체가 오기도 해 name만 본다.
  const name = typeof e === "object" && e !== null && "name" in e ? String(e.name) : "";
  const message = e instanceof Error ? e.message : String(e);
  switch (name) {
    case "NotAllowedError":
      return new CameraError("permission-denied", message);
    // 일부 브라우저·관리자 정책으로 막힌 경우. Chrome은 권한 정책 차단도 NotAllowedError로 보낸다
    case "SecurityError":
      return new CameraError("blocked", message);
    case "NotFoundError":
    case "OverconstrainedError":
      return new CameraError("not-found", message);
    case "NotReadableError":
    case "AbortError":
      return new CameraError("in-use", message);
    default:
      return new CameraError("unknown", message);
  }
}

export async function openCamera(deviceId: string | undefined, width: number, height: number) {
  // HTTPS나 localhost가 아니면 브라우저가 카메라 API 자체를 막는다.
  if (!window.isSecureContext) throw new CameraError("insecure", "보안 연결이 아닙니다");
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new CameraError("unsupported", "카메라를 지원하지 않는 브라우저입니다");
  }
  try {
    return await navigator.mediaDevices.getUserMedia({
      video: {
        ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "user" }),
        width: { ideal: width },
        height: { ideal: height },
      },
      audio: false,
    });
  } catch (e) {
    throw toCameraError(e);
  }
}

// 색 측정에 영향을 주는 카메라 제어. 지원 여부는 카메라·기기·브라우저마다 다르다.
const CONTROL_KEYS = [
  "exposureMode",
  "exposureTime",
  "exposureCompensation",
  "whiteBalanceMode",
  "colorTemperature",
  "focusMode",
  "focusDistance",
] as const;

export type ControlInfo = { key: string; capability: unknown; setting: unknown };

export function describeControls(track: MediaStreamTrack): ControlInfo[] {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  const settings = track.getSettings() as Record<string, unknown>;
  return CONTROL_KEYS.map((key) => ({ key, capability: caps[key], setting: settings[key] }));
}

// 노출·화이트밸런스·초점을 지금 상태로 고정한다. 현재 값 없이 manual로 바꾸면 기본값이 적용돼
// 화면이 어두워질 수 있어, single-shot이나 현재 값을 넣은 manual만 쓴다.
export type ControlName = "exposure" | "whiteBalance" | "focus";

/** 카메라가 알려 준 범위(min·max·step) 안으로 값을 맞춘다. 범위 정보가 없으면 그대로 둔다. */
function clampToRange(value: number, range: unknown): number {
  const r = range as { min?: number; max?: number; step?: number } | undefined;
  if (typeof r?.min !== "number" || typeof r?.max !== "number") return value;
  let v = Math.max(r.min, Math.min(r.max, value));
  if (r.step && r.step > 0) v = r.min + Math.round((v - r.min) / r.step) * r.step;
  return Math.max(r.min, Math.min(r.max, v));
}

export async function lockControls(
  track: MediaStreamTrack,
  names: ControlName[] = ["exposure", "whiteBalance", "focus"],
): Promise<Record<string, string>> {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  const settings = track.getSettings() as Record<string, unknown>;

  const targets = [
    { name: "exposure", mode: "exposureMode", value: "exposureTime" },
    { name: "whiteBalance", mode: "whiteBalanceMode", value: "colorTemperature" },
    { name: "focus", mode: "focusMode", value: "focusDistance" },
  ] as const;

  const results: Record<string, string> = {};
  for (const { name, mode, value } of targets) {
    if (!names.includes(name)) continue;
    const modes = caps[mode];
    if (!Array.isArray(modes)) {
      results[name] = "미지원";
      continue;
    }

    const current = settings[value];
    let constraint: Record<string, unknown> | null = null;
    if (modes.includes("single-shot")) {
      constraint = { [mode]: "single-shot" };
    } else if (modes.includes("manual") && typeof current === "number" && current > 0) {
      // 기기에 따라 현재 값이 허용 범위 밖으로 보고되어(예: 색온도) 그대로 넣으면 거절된다.
      constraint = { [mode]: "manual", [value]: clampToRange(current, caps[value]) };
    }

    if (!constraint) {
      // 현재 값을 0으로 알려 주는 기기(갤럭시탭 S6 Lite)에서 범위 최솟값으로 고정하면 화면이 어두워지거나
      // 색온도가 틀어진다. 지금 값을 모르면 고정하지 않고 자동으로 둔다.
      results[name] = modes.includes("manual")
        ? "고정 안 함 (기기가 현재 값을 알려 주지 않음)"
        : `고정 불가 (지원 모드: ${modes.join(", ")})`;
      continue;
    }
    try {
      await track.applyConstraints({ advanced: [constraint as MediaTrackConstraintSet] });
      results[name] = `고정됨 (${String(constraint[mode])})`;
    } catch (e) {
      // 일부 기기는 manual 전환 뒤 값 적용만 실패할 수 있다. 그 상태로 남기지 않고 자동으로 복구한다.
      if (modes.includes("continuous"))
        await track
          .applyConstraints({ advanced: [{ [mode]: "continuous" } as MediaTrackConstraintSet] })
          .catch(() => {});
      results[name] = `실패: ${e instanceof Error ? e.message : String(e)}`;
    }
  }
  return results;
}

/** 다시 자동으로 되돌린다. */
export async function unlockControls(track: MediaStreamTrack) {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  const constraint: Record<string, string> = {};
  for (const mode of ["exposureMode", "whiteBalanceMode", "focusMode"]) {
    const modes = caps[mode];
    if (Array.isArray(modes) && modes.includes("continuous")) constraint[mode] = "continuous";
  }
  await track.applyConstraints({ advanced: [constraint as MediaTrackConstraintSet] });
}

export type Range = { min: number; max: number; step?: number };

function validRange(value: unknown): Range | null {
  const range = value as Partial<Range> | null;
  if (
    typeof range?.min !== "number" ||
    typeof range.max !== "number" ||
    !Number.isFinite(range.min) ||
    !Number.isFinite(range.max) ||
    range.min > range.max
  )
    return null;
  const step =
    typeof range.step === "number" && Number.isFinite(range.step) && range.step > 0
      ? range.step
      : undefined;
  return { min: range.min, max: range.max, ...(step ? { step } : {}) };
}

export function exposureRange(track: MediaStreamTrack): Range | null {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  return validRange(caps.exposureTime);
}

/** 노출 맞추기에 쓰는 ISO. 갤럭시탭 S6은 이보다 올려도 더 밝아지지 않는다 */
const MATCH_ISO = 800;
/** 노출 시간 상한(100µs 단위). 100ms면 약 10fps라 이보다 길면 추적이 느려진다 */
const MATCH_MAX_EXPOSURE = 1000;
/** 자동 밝기와 이만큼(0~255) 안이면 맞춘 것으로 본다 */
const MATCH_TOLERANCE = 3;
const MATCH_TRIES = 4;
/** 값을 바꾼 뒤 화면에 반영되기까지 기다리는 시간(ms). 갤럭시탭 S6은 0.2~0.5초 뒤에 바뀐다 */
const SETTLE_MIN_MS = 600;
/** 값을 바꾼 뒤 화면이 자리 잡기를 기다리는 최대 시간(ms) */
const SETTLE_MAX_MS = 1500;
/** 처음 맞춰 볼 노출 시간(100µs 단위). 30fps 한 프레임이다 */
const MATCH_START_EXPOSURE = 333;

const aborted = () => new DOMException("카메라 잠금을 취소했습니다", "AbortError");
const checkActive = (signal?: AbortSignal) => {
  if (signal?.aborted) throw aborted();
};

/** 다음 영상 프레임을 기다린다. timeoutMs 안에 프레임이 오지 않으면 false다 */
const nextFrame = (video: HTMLVideoElement, timeoutMs: number, signal?: AbortSignal) =>
  new Promise<boolean>((resolve, reject) => {
    if (signal?.aborted) return reject(aborted());
    let frame: number | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const deadline = setTimeout(() => finish(false), Math.max(timeoutMs, 0));
    const cleanup = () => {
      signal?.removeEventListener("abort", cancel);
      if (frame !== null && "cancelVideoFrameCallback" in video)
        video.cancelVideoFrameCallback(frame);
      if (timer !== null) clearTimeout(timer);
      clearTimeout(deadline);
    };
    const finish = (arrived: boolean) => {
      cleanup();
      resolve(arrived);
    };
    const done = () => {
      frame = null;
      timer = null;
      finish(true);
    };
    const cancel = () => {
      cleanup();
      reject(aborted());
    };
    signal?.addEventListener("abort", cancel, { once: true });
    if (typeof video.requestVideoFrameCallback === "function")
      frame = video.requestVideoFrameCallback(done);
    else timer = setTimeout(done, 50);
  });

/** 프레임 평균 밝기(0~255). 자동 노출도 화면 전체를 보고 밝기를 정한다 */
function frameBrightness(video: HTMLVideoElement, canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return NaN;
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  let sum = 0;
  for (let i = 0; i < data.length; i += 4) sum += data[i] + data[i + 1] + data[i + 2];
  return sum / (data.length / 4) / 3;
}

/**
 * 값을 바꾼 뒤 화면에 반영될 때까지(SETTLE_MIN_MS) 기다리고, 밝기가 멈추면(연속 두 프레임 차이 1 안)
 * 그 밝기를 돌려준다. 바로 다음 프레임은 아직 바꾸기 전 화면이라 멈춘 것으로 보면 안 된다.
 * 영상이 멈춰 SETTLE_MAX_MS 안에 프레임이 하나도 오지 않으면 실패로 끝낸다
 */
async function settledBrightness(
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
  signal?: AbortSignal,
) {
  const started = performance.now();
  let prev = NaN;
  let elapsed: number;
  while ((elapsed = performance.now() - started) < SETTLE_MAX_MS) {
    const arrived = await nextFrame(video, SETTLE_MAX_MS - elapsed, signal);
    checkActive(signal);
    if (!arrived) break;
    const now = frameBrightness(video, canvas);
    if (performance.now() - started >= SETTLE_MIN_MS && Math.abs(now - prev) < 1) return now;
    prev = now;
  }
  if (Number.isNaN(prev)) throw new Error("영상 프레임이 오지 않습니다");
  return prev;
}

/**
 * 자동 노출일 때와 같은 밝기로 노출을 수동 고정한다.
 * 갤럭시탭 S6은 자동 중에 노출 시간·ISO를 실제와 다르게 알려 줘, 알려 준 값으로 고정(lockControls)하면
 * 화면이 어두워진다. ISO는 MATCH_ISO로 두고 밝기가 노출 시간에 비례한다고 보고 몇 번 재며 맞춘다.
 * 노출 시간·ISO를 지정할 수 없는 기기는 lockControls로 지금 값을 고정한다
 */
export async function matchExposure(
  track: MediaStreamTrack,
  video: HTMLVideoElement,
  signal?: AbortSignal,
): Promise<Record<string, string>> {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  const time = validRange(caps.exposureTime);
  const iso = validRange(caps.iso);
  const modes = caps.exposureMode;
  if (!time || !iso || !Array.isArray(modes) || !modes.includes("manual")) {
    checkActive(signal);
    const result = await lockControls(track, ["exposure"]);
    checkActive(signal);
    return result;
  }

  const canvas = document.createElement("canvas");
  canvas.width = 48;
  canvas.height = 64;
  const apply = async (c: Record<string, unknown>) => {
    checkActive(signal);
    await track.applyConstraints({ advanced: [c as MediaTrackConstraintSet] });
    checkActive(signal);
  };
  const isoValue = clampToRange(MATCH_ISO, iso);
  const maxTime = Math.max(time.min, Math.min(time.max, MATCH_MAX_EXPOSURE));
  const linear = (v: number) => (Math.max(v, 1) / 255) ** 2.2;

  try {
    await apply({ exposureMode: "continuous" });
    const target = await settledBrightness(video, canvas, signal);
    let exposure = Math.min(maxTime, clampToRange(MATCH_START_EXPOSURE, time));
    let appliedExposure: number | null = null;
    let best = { exposure, diff: Infinity, brightness: NaN };
    for (let i = 0; i < MATCH_TRIES; i++) {
      await apply({ exposureMode: "manual", exposureTime: exposure, iso: isoValue });
      appliedExposure = exposure;
      const brightness = await settledBrightness(video, canvas, signal);
      const diff = Math.abs(brightness - target);
      if (diff < best.diff) best = { exposure, diff, brightness };
      if (diff <= MATCH_TOLERANCE) break;
      const next = Math.min(
        maxTime,
        clampToRange((exposure * linear(target)) / linear(brightness), time),
      );
      if (next === exposure) break;
      exposure = next;
    }
    if (best.exposure !== appliedExposure)
      await apply({ exposureMode: "manual", exposureTime: best.exposure, iso: isoValue });
    return {
      exposure: `고정됨 (노출 ${Math.round(best.exposure)} · ISO ${isoValue}, 밝기 ${Math.round(target)} → ${Math.round(best.brightness)})`,
    };
  } catch (e) {
    if (signal?.aborted) throw e;
    await apply({ exposureMode: "continuous" }).catch(() => {});
    return { exposure: `실패: ${e instanceof Error ? e.message : String(e)}` };
  }
}

/** 노출 시간을 직접 지정한다. 조명이 고정된 환경에서 적당한 밝기를 찾는 용도. */
export async function setExposureTime(track: MediaStreamTrack, exposureTime: number) {
  await track.applyConstraints({
    advanced: [{ exposureMode: "manual", exposureTime } as MediaTrackConstraintSet],
  });
}
