"use client";

import { useEffect, useRef, useState } from "react";

import { GRID, MEASURED, SKIN } from "./spec";
import type { GaugeDisplay } from "./stability";
import type { GaugeBaselineStatus } from "./use-gauge-baseline";
import type { GaugeReading } from "./use-gauge-measure";

const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "-" : v.toFixed(digits);

/** 얼굴 지도 칸 표. 맨피부는 옅게, 그 단계 영역은 분홍, 재는 하위 단계 영역은 빨강 */
function CellMap({ areas, made }: { areas: Uint8Array[]; made: Uint8Array | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    const image = ctx.createImageData(GRID, GRID);
    for (let k = 0; k < GRID * GRID; k++) {
      const area = areas.some((cells) => cells[k]);
      const rgb = area
        ? [239, 68, 68]
        : made?.[k]
          ? [244, 170, 190]
          : SKIN[k]
            ? [90, 90, 90]
            : MEASURED[k]
              ? [50, 50, 50]
              : [0, 0, 0];
      image.data.set([...rgb, 255], k * 4);
    }
    ctx.putImageData(image, 0, 0);
  }, [areas, made]);
  return <canvas ref={ref} width={GRID} height={GRID} className="size-32 rounded" />;
}

/**
 * 게이지 경계값을 실기기에서 잡을 수 있게 잰 값과 못 잰 이유를 띄운다(개발 도구에서만).
 * 칸 표는 켜고 끌 수 있다
 */
export function GaugeDebug({
  baseline,
  reading,
  display,
  areas,
  made,
}: {
  baseline: GaugeBaselineStatus;
  reading: GaugeReading | null;
  display: GaugeDisplay | null;
  areas: Uint8Array[];
  made: Uint8Array | null;
}) {
  const [showCells, setShowCells] = useState(false);
  const m = reading?.measure;
  const rows: [string, string][] = [
    [
      "기준",
      `${baseline.bare ? "맨얼굴 완료" : `사진 ${baseline.frames}/15`} · 흰자 ${baseline.white ? baseline.white.map((v) => v.toFixed(0)).join(",") : "-"}`,
    ],
    ["잠금", baseline.lock ? Object.values(baseline.lock).join(" · ") : "-"],
    [
      "사진",
      `${reading?.frame ?? "통과"} · 흔들림 ${num(reading?.drift)} · ${num(reading?.ms, 1)}ms`,
    ],
    [
      "잰 값",
      `비율 ${num(m?.ratio)} · 막대 ${num(m?.bar, 1)} · 목표 ${num(m?.target)} · ${m?.reason ?? ""}`,
    ],
    [
      "색감",
      `hue ${num(m?.hue, 1)} · chroma ${num(m?.chroma, 1)} · 비슷 ${m?.hueSame ?? "-"}/${m?.chromaSame ?? "-"}`,
    ],
    [
      "좌우",
      m?.sides
        .map((s) => `${s.region} ${num(s.ratio)}(${s.cells}칸${s.reason ? ` ${s.reason}` : ""})`)
        .join(" · ") || "-",
    ],
    [
      "보임",
      `${display?.label ?? "-"} · 막대 ${num(display?.bar, 1)}${display?.stale ? " · 유지" : ""} · ${display?.reason ?? ""}`,
    ],
  ];
  return (
    <div className="pointer-events-auto fixed top-2 left-2 z-50 flex max-w-[420px] flex-col gap-1 rounded bg-black/80 p-2 text-xs text-white">
      {rows.map(([name, value]) => (
        <div key={name} className="flex gap-2">
          <span className="w-10 shrink-0 text-white/60">{name}</span>
          <span className="tabular">{value}</span>
        </div>
      ))}
      <label className="flex items-center gap-1">
        <input
          type="checkbox"
          checked={showCells}
          onChange={(e) => setShowCells(e.target.checked)}
        />
        영역 칸
      </label>
      {showCells && <CellMap areas={areas} made={made} />}
    </div>
  );
}
