"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DEFAULT_SMOOTHING as SMOOTHING,
  FaceTracker,
  isGuideVisible,
  REGIONS,
  REGION_NAMES,
} from "@/features/face";
import type { CloseUpMode, FaceFrame, RegionName, TrackerStats } from "@/features/face";

import {
  describeControls,
  listCameras,
  exposureRange,
  lockControls,
  openCamera,
  setExposureTime,
  unlockControls,
  type ControlName,
  type Range,
  RESOLUTIONS,
  type ControlInfo,
} from "./camera";
import { ColorProbe, type ColorStats } from "./color-probe";

const REGION_COLORS: Record<RegionName, string> = {
  leftEye: "#38bdf8",
  rightEye: "#38bdf8",
  leftBrow: "#a78bfa",
  rightBrow: "#a78bfa",
  lipsOuter: "#f472b6",
  lipsInner: "#fb7185",
  leftCheek: "#fb923c",
  rightCheek: "#fb923c",
  faceOval: "#4ade80",
};

const toDeg = (rad: number) => Math.round((rad * 180) / Math.PI);
const fmtLab = (v: { l: number; a: number; b: number }) =>
  `${v.l.toFixed(1)} / ${v.a.toFixed(1)} / ${v.b.toFixed(1)}`;

// 화면은 거울처럼 좌우 반전해서 보여준다. 글자가 뒤집히지 않도록 CSS 대신 좌표를 반전해 그린다.
function draw(canvas: HTMLCanvasElement, frame: FaceFrame | null, showIndices: boolean) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!frame || frame.trackingState === "lost") return;

  const { width, height } = canvas;
  const px = (i: number) => ({
    x: (1 - frame.landmarks[i].x) * width,
    y: frame.landmarks[i].y * height,
  });

  ctx.fillStyle = "rgba(255,255,255,0.35)";
  for (let i = 0; i < frame.landmarks.length; i++) {
    const { x, y } = px(i);
    ctx.fillRect(x - 1, y - 1, 2, 2);
  }

  // 가이드를 보여주지 않는 상태의 부위는 회색으로 그린다.
  for (const name of REGION_NAMES) {
    ctx.fillStyle = isGuideVisible(frame, name) ? REGION_COLORS[name] : "rgba(160,160,160,0.6)";
    for (const i of REGIONS[name].indices) {
      const { x, y } = px(i);
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (showIndices) {
    ctx.fillStyle = "#fff";
    ctx.font = "9px sans-serif";
    for (let i = 0; i < 468; i++) {
      const { x, y } = px(i);
      ctx.fillText(String(i), x + 2, y - 2);
    }
  }
}

type Hud = { frame: FaceFrame | null; stats: TrackerStats; color: ColorStats | null };

export default function DebugFacePage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trackerRef = useRef<FaceTracker | null>(null);
  const probeRef = useRef<ColorProbe | null>(null);
  const showIndicesRef = useRef(false);
  const lastHudUpdate = useRef(0);

  const [status, setStatus] = useState<"idle" | "starting" | "running" | "error">("idle");
  const [error, setError] = useState("");
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>();
  const [resolution, setResolution] = useState(1);
  const [controls, setControls] = useState<ControlInfo[]>([]);
  const [lockResult, setLockResult] = useState<Record<string, string> | null>(null);
  const [exposure, setExposure] = useState<{ range: Range; value: number } | null>(null);
  const [showIndices, setShowIndices] = useState(false);
  const [closeUp, setCloseUp] = useState<CloseUpMode>("auto");
  const [smoothing, setSmoothing] = useState(true);
  const [hud, setHud] = useState<Hud | null>(null);

  useEffect(() => {
    showIndicesRef.current = showIndices;
  }, [showIndices]);

  useEffect(() => {
    trackerRef.current?.setOptions({ closeUp, smoothing: smoothing ? SMOOTHING : null });
  }, [closeUp, smoothing]);

  useEffect(() => {
    const video = videoRef.current;
    return () => {
      trackerRef.current?.dispose();
      (video?.srcObject as MediaStream | null)?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function connect(nextDeviceId: string | undefined, nextResolution: number) {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    (video.srcObject as MediaStream | null)?.getTracks().forEach((t) => t.stop());
    const { width, height } = RESOLUTIONS[nextResolution];
    const stream = await openCamera(nextDeviceId, width, height);
    video.srcObject = stream;
    await video.play();
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const track = stream.getVideoTracks()[0];
    setDeviceId(track.getSettings().deviceId);
    setControls(describeControls(track));
    setLockResult(null);
    const range = exposureRange(track);
    const current = (track.getSettings() as Record<string, unknown>).exposureTime;
    setExposure(range ? { range, value: typeof current === "number" ? current : range.min } : null);
    // 카메라 이름은 권한을 받은 뒤에야 보인다.
    setCameras(await listCameras());
  }

  async function start() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    setStatus("starting");
    try {
      await connect(deviceId, resolution);
      probeRef.current = new ColorProbe();
      // 오류 뒤 다시 시작할 때 이전 추적기의 모델이 남지 않게 정리한다.
      trackerRef.current?.dispose();
      trackerRef.current = new FaceTracker(
        video,
        (frame, stats) => {
          draw(canvas, frame, showIndicesRef.current);
          const now = performance.now();
          if (now - lastHudUpdate.current > 200) {
            lastHudUpdate.current = now;
            const color =
              frame && frame.trackingState !== "lost"
                ? (probeRef.current?.sample(video, frame) ?? null)
                : null;
            setHud({ frame, stats: { ...stats }, color });
          }
        },
        { closeUp, smoothing: smoothing ? SMOOTHING : null },
      );
      await trackerRef.current.start();
      setStatus("running");
    } catch (e) {
      setError(String(e));
      setStatus("error");
    }
  }

  async function change(nextDeviceId: string | undefined, nextResolution: number) {
    try {
      await connect(nextDeviceId, nextResolution);
      setResolution(nextResolution);
    } catch (e) {
      setError(String(e));
    }
  }

  function currentTrack() {
    return (videoRef.current?.srcObject as MediaStream | null)?.getVideoTracks()[0];
  }

  async function lock(names: ControlName[]) {
    const track = currentTrack();
    if (!track) return;
    setLockResult(await lockControls(track, names));
    setControls(describeControls(track));
  }

  async function changeExposure(value: number) {
    const track = currentTrack();
    if (!track || !exposure) return;
    setExposure({ ...exposure, value });
    try {
      await setExposureTime(track, value);
      setLockResult({ exposure: `수동 ${value}` });
    } catch (e) {
      setLockResult({ exposure: `실패: ${String(e)}` });
    }
    setControls(describeControls(track));
  }

  async function unlock() {
    const track = currentTrack();
    if (!track) return;
    try {
      await unlockControls(track);
      setLockResult({ 자동: "되돌림" });
    } catch (e) {
      setLockResult({ 자동: `실패: ${String(e)}` });
    }
    setControls(describeControls(track));
  }

  const frame = hud?.frame;
  const running = status === "running";

  return (
    <main className="flex flex-1 flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={start} disabled={status === "starting" || running}>
          카메라 시작
        </Button>
        <select
          className="h-8 rounded-lg border bg-background px-2 text-sm"
          value={deviceId ?? ""}
          disabled={!running}
          onChange={(e) => change(e.target.value, resolution)}
        >
          {cameras.length === 0 && <option value="">카메라 목록 (시작 후 표시)</option>}
          {cameras.map((c, i) => (
            <option key={c.deviceId} value={c.deviceId}>
              {c.label || `카메라 ${i + 1}`}
            </option>
          ))}
        </select>
        <select
          className="h-8 rounded-lg border bg-background px-2 text-sm"
          value={resolution}
          onChange={(e) =>
            running
              ? change(deviceId, Number(e.target.value))
              : setResolution(Number(e.target.value))
          }
        >
          {RESOLUTIONS.map((r, i) => (
            <option key={r.label} value={i}>
              {r.label}
            </option>
          ))}
        </select>
        <Button variant="outline" onClick={() => lock(["whiteBalance"])} disabled={!running}>
          WB 고정
        </Button>
        <Button variant="outline" onClick={() => lock(["focus"])} disabled={!running}>
          초점 고정
        </Button>
        <Button variant="outline" onClick={() => lock(["exposure"])} disabled={!running}>
          노출 고정
        </Button>
        <Button variant="outline" onClick={unlock} disabled={!running}>
          자동으로
        </Button>
      </div>

      {exposure && running && (
        <label className="flex max-w-3xl items-center gap-2 text-sm">
          노출 시간
          <input
            type="range"
            className="flex-1"
            min={exposure.range.min}
            max={exposure.range.max}
            step={exposure.range.step ?? 1}
            value={exposure.value}
            onChange={(e) => changeExposure(Number(e.target.value))}
          />
          <span className="w-16 text-right font-mono">{exposure.value}</span>
        </label>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => setShowIndices((v) => !v)}>
          랜드마크 번호 {showIndices ? "숨기기" : "표시"}
        </Button>
        <Button
          variant="outline"
          onClick={() => setCloseUp((m) => (m === "auto" ? "on" : m === "on" ? "off" : "auto"))}
        >
          근접 모드: {closeUp}
        </Button>
        <Button variant="outline" onClick={() => setSmoothing((v) => !v)}>
          떨림 보정: {smoothing ? "on" : "off"}
        </Button>
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>

      <div className="relative w-full max-w-3xl">
        <video ref={videoRef} className="w-full -scale-x-100" playsInline muted />
        <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      </div>

      {hud && (
        <dl className="grid max-w-3xl grid-cols-2 gap-x-4 gap-y-1 font-mono text-sm sm:grid-cols-4">
          <dt>state</dt>
          <dd>{frame?.trackingState ?? "acquiring"}</dd>
          <dt>fps</dt>
          <dd>{hud.stats.fps}</dd>
          <dt>detect</dt>
          <dd>{hud.stats.detectMs.toFixed(1)} ms</dd>
          <dt>입력 축소 배율</dt>
          <dd>{hud.stats.inputScale.toFixed(2)}</dd>
          <dt>video</dt>
          <dd>{frame ? `${frame.imageSize.width}×${frame.imageSize.height}` : "-"}</dd>
          <dt>iod</dt>
          <dd>{frame ? frame.iod.toFixed(1) : "-"} px</dd>
          <dt>yaw / pitch / roll</dt>
          <dd>
            {frame
              ? `${toDeg(frame.pose.yaw)} / ${toDeg(frame.pose.pitch)} / ${toDeg(frame.pose.roll)}°`
              : "-"}
          </dd>
          <dt>eye L / R</dt>
          <dd>
            {frame
              ? `${frame.eyes.left.openness.toFixed(2)} / ${frame.eyes.right.openness.toFixed(2)}`
              : "-"}
          </dd>
          <dt>eyeBlink L / R (원본)</dt>
          <dd>{`${hud.stats.blink.left.toFixed(2)} / ${hud.stats.blink.right.toFixed(2)}`}</dd>
          <dt>이마 색 (L / a / b)</dt>
          <dd>{hud.color ? fmtLab(hud.color.mean) : "-"}</dd>
          <dt>색 흔들림 (ΔE)</dt>
          <dd className={hud.color && hud.color.jitter > 1 ? "text-destructive" : undefined}>
            {hud.color
              ? `${hud.color.jitter.toFixed(2)} ${hud.color.jitter > 1 ? "불안정" : "안정"}`
              : "-"}
          </dd>
        </dl>
      )}

      {controls.length > 0 && (
        <section className="max-w-3xl font-mono text-xs">
          <h2 className="mb-1 text-sm font-semibold">카메라 제어 (지원 범위 / 현재 값)</h2>
          <ul>
            {controls.map((c) => (
              <li key={c.key}>
                {c.key}: {c.capability === undefined ? "미지원" : JSON.stringify(c.capability)} /{" "}
                {c.setting === undefined ? "-" : JSON.stringify(c.setting)}
              </li>
            ))}
          </ul>
          {lockResult && (
            <ul className="mt-1">
              {Object.entries(lockResult).map(([k, v]) => (
                <li key={k}>
                  {k}: {v}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
