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

    let constraint: Record<string, unknown> | null = null;
    if (modes.includes("single-shot")) {
      constraint = { [mode]: "single-shot" };
    } else if (modes.includes("manual") && settings[value] !== undefined) {
      constraint = { [mode]: "manual", [value]: settings[value] };
    }

    if (!constraint) {
      results[name] = `고정 불가 (지원 모드: ${modes.join(", ")})`;
      continue;
    }
    try {
      await track.applyConstraints({ advanced: [constraint as MediaTrackConstraintSet] });
      results[name] = `고정됨 (${String(constraint[mode])})`;
    } catch (e) {
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

export function exposureRange(track: MediaStreamTrack): Range | null {
  const caps = (track.getCapabilities?.() ?? {}) as Record<string, unknown>;
  const range = caps.exposureTime as Range | undefined;
  return range && typeof range.min === "number" ? range : null;
}

/** 노출 시간을 직접 지정한다. 조명이 고정된 환경에서 적당한 밝기를 찾는 용도. */
export async function setExposureTime(track: MediaStreamTrack, exposureTime: number) {
  await track.applyConstraints({
    advanced: [{ exposureMode: "manual", exposureTime } as MediaTrackConstraintSet],
  });
}
