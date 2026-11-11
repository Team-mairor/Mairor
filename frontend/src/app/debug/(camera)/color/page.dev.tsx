"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  lockControls,
  REGIONS,
  toScreen,
  unlockControls,
  useCamera,
  useFaceFrame,
  type FaceFrame,
  type RegionName,
} from "@/features/face";
import type { Lab } from "@/lib/color";

import { matchLock } from "./match-lock";
import { deltaE, grow, mean, meanLab, sampleRegion, sd, type Px } from "./region-color";

type Target = {
  key: string;
  label: string;
  region: RegionName;
  band: number;
  hole?: RegionName;
};

/** 둘레 띠 배율은 띠가 다른 부위에 걸리지 않을 만큼만 키운다 */
const TARGETS: Target[] = [
  { key: "lips", label: "입술", region: "lipsOuter", band: 1.5, hole: "lipsInner" },
  { key: "leftCheek", label: "왼볼", region: "leftCheek", band: 1.25 },
  { key: "rightCheek", label: "오른볼", region: "rightCheek", band: 1.25 },
  { key: "leftBrow", label: "왼눈썹", region: "leftBrow", band: 1.5 },
  { key: "rightBrow", label: "오른눈썹", region: "rightBrow", band: 1.5 },
];

/** 실시간 흔들림을 보는 구간(ms) */
const WINDOW_MS = 1000;
const RECORD_MS = 3000;
const STORE_KEY = "mairor-color-measure";
/** 화면에 보이는 최근 기록 수 */
const SHOWN = 3;

type Point = { t: number; inner: Lab; band: Lab; contrast: number };
type Live = { inner: Lab; band: Lab; contrast: number; jitter: number };
type Summary = { contrast: number; contrastSd: number; inner: Lab; band: Lab; n: number };
type Entry = {
  label: string;
  targets: { [key: string]: Summary | null };
  camera: { [key: string]: unknown };
};

const fmt = (v: Lab) => `${v.l.toFixed(1)} ${v.a.toFixed(1)} ${v.b.toFixed(1)}`;

/** 영상 픽셀 좌표의 부위 외곽선 */
const outline = (frame: FaceFrame, region: RegionName): Px[] =>
  REGIONS[region].indices.map((i) => ({
    x: frame.landmarks[i].x * frame.imageSize.width,
    y: frame.landmarks[i].y * frame.imageSize.height,
  }));

function loadRecords(): Entry[] {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY) ?? "[]") as Entry[];
  } catch {
    return [];
  }
}

/** 화장 전후 색 차이 측정(개발용). 부위 안과 둘레 피부의 색 차이와 그 흔들림을 잰다 */
export default function ColorMeasurePage() {
  const { videoRef, viewTransform } = useCamera();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const grabRef = useRef<HTMLCanvasElement | null>(null);
  const history = useRef<{ [key: string]: Point[] }>({});
  const recording = useRef<{ until: number; points: { [key: string]: Point[] } } | null>(null);
  const lastHud = useRef(0);
  const viewRef = useRef(viewTransform);

  const [live, setLive] = useState<{ [key: string]: Live | null }>({});
  const [label, setLabel] = useState("맨얼굴");
  const [busy, setBusy] = useState(false);
  const [records, setRecords] = useState<Entry[]>([]);
  const [lockResult, setLockResult] = useState<{ [key: string]: string }>({});
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    viewRef.current = viewTransform;
  }, [viewTransform]);

  useEffect(() => {
    // 기록은 브라우저 저장소에서만 읽을 수 있다
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setRecords(loadRecords());
  }, []);

  const track = () =>
    (videoRef.current?.srcObject as MediaStream | null)?.getVideoTracks()[0] ?? null;

  const draw = (frame: FaceFrame | null) => {
    const canvas = canvasRef.current;
    const view = viewRef.current;
    if (!canvas) return;
    if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
      canvas.width = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!frame || !view || frame.trackingState !== "tracking") return;
    // 좌표 변환은 영상 기준이라, 위쪽 머리글만큼 내려온 이 캔버스 기준으로 옮긴다
    const video = videoRef.current?.getBoundingClientRect();
    const box = canvas.getBoundingClientRect();
    const dx = video ? video.left - box.left : 0;
    const dy = video ? video.top - box.top : 0;
    const toView = (p: Px) => {
      const q = toScreen(
        { x: p.x / frame.imageSize.width, y: p.y / frame.imageSize.height },
        frame.imageSize,
        view,
      );
      return { x: q.x + dx, y: q.y + dy };
    };
    const path = (poly: Px[], dashed: boolean) => {
      ctx.setLineDash(dashed ? [8, 6] : []);
      ctx.beginPath();
      poly.map(toView).forEach((p) => ctx.lineTo(p.x, p.y));
      ctx.closePath();
      ctx.stroke();
    };
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#f0f";
    for (const t of TARGETS) {
      const poly = outline(frame, t.region);
      path(poly, false);
      path(grow(poly, t.band), true);
      if (t.hole) path(outline(frame, t.hole), false);
    }
  };

  const finish = (points: { [key: string]: Point[] }) => {
    const targets: Entry["targets"] = {};
    for (const t of TARGETS) {
      const list = points[t.key] ?? [];
      targets[t.key] = list.length
        ? {
            contrast: mean(list.map((p) => p.contrast)),
            contrastSd: sd(list.map((p) => p.contrast)),
            inner: meanLab(list.map((p) => p.inner)),
            band: meanLab(list.map((p) => p.band)),
            n: list.length,
          }
        : null;
    }
    const settings = (track()?.getSettings() ?? {}) as { [key: string]: unknown };
    const camera = Object.fromEntries(
      ["exposureMode", "exposureTime", "whiteBalanceMode", "colorTemperature", "focusMode"].map(
        (k) => [k, settings[k]],
      ),
    );
    // 이 기기는 노출 값을 실제와 다르게 알려 줘, 고정 결과도 함께 남긴다
    const next = [...loadRecords(), { label, targets, camera: { ...camera, lock: lockResult } }];
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(next));
    } catch {
      // 저장하지 못해도 화면 결과는 남는다
    }
    setRecords(next);
    setBusy(false);
  };

  useFaceFrame((frame) => {
    draw(frame);
    const video = videoRef.current;
    if (!video || !frame || frame.trackingState !== "tracking") return;
    const { width, height } = frame.imageSize;
    const canvas = (grabRef.current ??= document.createElement("canvas"));
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, width, height);
    const image = ctx.getImageData(0, 0, width, height);

    const now = frame.timestamp;
    const rec = recording.current;
    const next: { [key: string]: Live | null } = {};
    const face = outline(frame, "faceOval");
    for (const t of TARGETS) {
      const hole = t.hole ? outline(frame, t.hole) : null;
      // 둘레 띠가 얼굴 밖 머리카락·배경에 걸리면 고개를 조금만 움직여도 값이 크게 흔들려 윤곽 안으로 자른다
      const s = sampleRegion(image, outline(frame, t.region), t.band, hole, face);
      const list = (history.current[t.key] ??= []);
      if (s) {
        const point = { t: now, inner: s.inner, band: s.band, contrast: deltaE(s.inner, s.band) };
        list.push(point);
        if (rec && now <= rec.until) (rec.points[t.key] ??= []).push(point);
      }
      while (list.length && now - list[0].t > WINDOW_MS) list.shift();
      const last = list[list.length - 1];
      next[t.key] =
        s && last
          ? {
              inner: last.inner,
              band: last.band,
              contrast: last.contrast,
              jitter: sd(list.map((p) => p.contrast)),
            }
          : null;
    }

    if (rec && now > rec.until) {
      recording.current = null;
      finish(rec.points);
    }
    if (now - lastHud.current > 200) {
      lastHud.current = now;
      setLive(next);
    }
  });

  const record = () => {
    setBusy(true);
    setCopied(false);
    const rec = { until: performance.now() + RECORD_MS, points: {} };
    recording.current = rec;
    // 얼굴을 놓쳐 프레임이 오지 않아도 기록을 끝낸다
    setTimeout(() => {
      if (recording.current !== rec) return;
      recording.current = null;
      finish(rec.points);
    }, RECORD_MS + 500);
  };

  const lock = async () => {
    const t = track();
    const video = videoRef.current;
    if (!t || !video) return;
    setLockResult({ 고정: "자동일 때 밝기·색에 맞추는 중…" });
    try {
      const matched = await matchLock(t, video);
      const focus = await lockControls(t, ["focus"]);
      setLockResult({ ...matched, ...focus });
    } catch (e) {
      setLockResult({ 고정: `실패: ${String(e)}` });
    }
  };

  const unlock = async () => {
    const t = track();
    if (!t) return;
    try {
      await unlockControls(t);
      setLockResult({ 자동: "되돌림" });
    } catch (e) {
      setLockResult({ 자동: `실패: ${String(e)}` });
    }
  };

  const clear = () => {
    localStorage.removeItem(STORE_KEY);
    setRecords([]);
  };

  const copy = async () => {
    await navigator.clipboard.writeText(JSON.stringify(records, null, 2));
    setCopied(true);
  };

  return (
    <main className="relative flex min-h-0 flex-1 flex-col">
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />

      <section className="relative mt-auto max-h-[55%] overflow-y-auto bg-background/85 p-3 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" onClick={lock}>
            밝기·색 맞춰 고정
          </Button>
          <Button variant="outline" onClick={unlock}>
            자동으로
          </Button>
          <span className="font-mono text-xs">
            {Object.entries(lockResult)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ")}
          </span>
        </div>

        <table className="mt-2 w-full font-mono text-xs">
          <thead>
            <tr className="text-left">
              <th>부위</th>
              <th>안 L a b</th>
              <th>둘레 L a b</th>
              <th>차이 ΔE</th>
              <th>1초 흔들림</th>
            </tr>
          </thead>
          <tbody>
            {TARGETS.map((t) => {
              const v = live[t.key];
              return (
                <tr key={t.key}>
                  <td>{t.label}</td>
                  <td>{v ? fmt(v.inner) : "-"}</td>
                  <td>{v ? fmt(v.band) : "-"}</td>
                  <td>{v ? v.contrast.toFixed(1) : "-"}</td>
                  <td>{v ? v.jitter.toFixed(2) : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            className="h-8 w-32 rounded-lg border bg-background px-2"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            aria-label="기록 이름"
          />
          <Button onClick={record} disabled={busy || !label.trim()}>
            {busy ? "기록 중…" : `${RECORD_MS / 1000}초 기록`}
          </Button>
          <Button variant="outline" onClick={copy} disabled={!records.length}>
            {copied ? "복사했어요" : "JSON 복사"}
          </Button>
          <Button variant="outline" onClick={clear} disabled={!records.length}>
            기록 지우기
          </Button>
        </div>

        {records.length > 0 && (
          <table className="mt-2 w-full font-mono text-xs">
            <thead>
              <tr className="text-left">
                <th>기록 ({records.length})</th>
                {TARGETS.map((t) => (
                  <th key={t.key}>{t.label} ΔE ± 흔들림</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* 얼굴을 가리지 않게 최근 기록만 보인다. 전체는 JSON 복사로 */}
              {records.slice(-SHOWN).map((r, i) => (
                <tr key={i}>
                  <td>{r.label}</td>
                  {TARGETS.map((t) => {
                    const s = r.targets[t.key];
                    return (
                      <td key={t.key}>
                        {s ? `${s.contrast.toFixed(1)} ± ${s.contrastSd.toFixed(2)}` : "-"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
