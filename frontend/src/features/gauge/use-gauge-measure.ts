"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { areaCells, madeCells } from "@/domain/gauge/area";
import type { Baseline } from "@/domain/gauge/baseline";
import { readCells, type CellLab } from "@/domain/gauge/cells";
import { areaCover, blankCovered, readCover } from "@/domain/gauge/cover";
import { frameState } from "@/domain/gauge/frame";
import { drift, lightChange } from "@/domain/gauge/light";
import {
  framesMedian,
  linearOfSrgb,
  measure,
  userSide,
  type Measure,
  type SideInput,
} from "@/domain/gauge/measure";
import {
  frameReason,
  GaugeStabilizer,
  WINDOW,
  windowReason,
  type FrameReason,
  type FrameState,
  type GaugeDisplay,
} from "@/domain/gauge/stability";
import { evaluateStep, type StepEvaluation } from "@/domain/gauge/step-evaluation";
import type { SelectedProduct } from "@/domain/gauge/substitute";
import { FRAME_STALE_MS, useCamera, useFaceFrame, type FaceFrame } from "@/vision/face";
import type { AreaGuideSet, GaugeReference } from "@/vision/guide";
import { OcclusionRunner, type OcclusionStatus } from "@/vision/occlusion";
import { loadFaceMesh, type FaceMesh } from "@/vision/overlay";

import { loadCellSampler, videoReader, type Samplers } from "./use-gauge-baseline";

export interface GaugeMeasureInput {
  /** 재는 중인지. 단계 카드가 닫히고 게이지를 보일 단계일 때만 참이다 */
  active: boolean;
  /** 바뀌면 다듬던 값을 버리고 처음부터 잰다(하위 단계 ID) */
  key: string | null;
  makeup: string;
  gauge: GaugeReference | null;
  /** 재는 하위 단계의 영역 묶음. 좌우 짝 부위는 묶음마다 따로 잰다 */
  guideSets: AreaGuideSet[];
  /** 그 단계 모든 하위 단계의 영역 묶음. 조명 재기에서 뺀다 */
  madeSets: AreaGuideSet[];
  /** 그 단계 시작 기준 */
  start: Baseline | null;
  /** 맨얼굴 기준 때 잰 흰자 색(sRGB 0~255) */
  white: [number, number, number] | null;
  /** 디버그에 띄울 한 번 잰 값(reading)을 낼지 */
  debug?: boolean;
  /** 0.2초마다 읽은 사진. 묶음 안 다음 단계 시작 기준을 잡으려고 넘긴다 */
  onShot?: (at: number, state: FrameState, grid: CellLab | null) => void;
}

/** 디버그에 띄우는 한 번 잰 값 */
export interface GaugeReading {
  measure: Measure | null;
  /** 이번 사진을 거른 이유. 쓸 수 있으면 null */
  frame: FrameReason | null;
  /** 맨피부가 단계 시작 기준에서 바뀐 크기(ΔE2000) */
  drift: number | null;
  /** 한 번 재는 데 걸린 시간(ms) */
  ms: number;
  /** 지금 하위 단계 영역 가린 몫(0~1). 가림 표가 없으면 null */
  cover: number | null;
  /** 가림 찾기 모델 상태 */
  occlusion: OcclusionStatus | null;
}

const sameDisplay = (a: GaugeDisplay | null, b: GaugeDisplay) =>
  !!a && (Object.keys(b) as (keyof GaugeDisplay)[]).every((k) => a[k] === b[k]);

/** 조명 변화를 다시 내는 간격(ms). 칸마다 넓게 흐려 무거워 사진마다 내지 않는다 */
const LIGHT_EVERY_MS = 1000;

interface Shot {
  at: number;
  reason: FrameReason | null;
  grid: CellLab | null;
}

/**
 * 튜토리얼 게이지 값을 브라우저에서 잰다(shared/gauge 「게이지 값 계산」 · 「측정 불가 판정과 값 안정화」).
 * 0.2초마다 사진을 거르고, 최근 1초 동안 쓸 수 있는 사진의 칸 색 가운데 값으로 재서 다듬는다.
 * 잰 값은 이번 실행 화면에만 쓰고 보내거나 저장하지 않는다
 */
export function useGaugeMeasure(input: GaugeMeasureInput) {
  const { videoRef } = useCamera();
  const [display, setDisplay] = useState<GaugeDisplay | null>(null);
  const [reading, setReading] = useState<GaugeReading | null>(null);
  const [mesh, setMesh] = useState<FaceMesh | null>(null);
  const samplers = useRef<Samplers | null>(null);
  const read = useRef(videoReader());
  const shots = useRef<Shot[]>([]);
  const stabilizer = useRef(new GaugeStabilizer(true));
  const last = useRef(-Infinity);
  const lightCache = useRef<{ at: number; light: CellLab } | null>(null);
  const latest = useRef(input);

  useEffect(() => {
    latest.current = input;
  });

  useEffect(() => {
    let live = true;
    Promise.all([loadFaceMesh(), loadCellSampler()])
      .then(([m, s]) => {
        if (!live) return;
        samplers.current = s;
        setMesh(m);
      })
      .catch((e) => console.warn("게이지를 잴 얼굴 지도를 불러오지 못했습니다", e));
    return () => {
      live = false;
    };
  }, []);

  // 하위 단계가 바뀌면 다듬던 값과 모은 사진을 버린다
  useEffect(() => {
    stabilizer.current = new GaugeStabilizer(true);
    shots.current = [];
    lightCache.current = null;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDisplay(null);
    setReading(null);
  }, [input.key]);

  const areas = useMemo(
    () => (mesh ? input.guideSets.map((set) => ({ set, cells: areaCells(set, mesh) })) : []),
    [mesh, input.guideSets],
  );
  const made = useMemo(
    () => (mesh ? madeCells(input.madeSets.map((set) => areaCells(set, mesh))) : null),
    [mesh, input.madeSets],
  );
  /** 지금 하위 단계 영역 칸 전체. 영역 가린 몫을 낼 때 쓴다 */
  const current = useMemo(() => madeCells(areas.map(({ cells }) => cells)), [areas]);
  const areasRef = useRef({ areas, made, current });
  useEffect(() => {
    areasRef.current = { areas, made, current };
  }, [areas, made, current]);

  // 가림 찾기 모델. 가이드에 재는 영역이 있으면 미리 열어 첫 측정부터 쓸 수 있게 한다
  const occlusion = useRef<OcclusionRunner | null>(null);
  const hasAreas = input.guideSets.length > 0;
  useEffect(() => {
    const runner = new OcclusionRunner();
    occlusion.current = runner;
    return () => {
      runner.dispose();
      occlusion.current = null;
    };
  }, []);
  useEffect(() => {
    if (hasAreas) occlusion.current?.start();
  }, [hasAreas]);

  useFaceFrame((frame: FaceFrame | null) => {
    const now = performance.now();
    const { active, makeup, gauge, start, white, guideSets, debug, onShot } = latest.current;
    const video = videoRef.current;
    if (!active || !video || !samplers.current) return;
    // 얼굴 지도를 막 불러와 영역을 아직 못 고른 틱은 건너뛴다
    if (guideSets.length && !areasRef.current.areas.length) return;
    if (now - last.current < WINDOW.intervalMs) return;
    last.current = now;
    const started = performance.now();

    const fresh = frame && now - (frame.detectedAt ?? frame.timestamp) <= FRAME_STALE_MS;
    const pixels = fresh ? read.current(video) : null;
    const state = frameState(fresh ? frame : null, pixels);
    let grid: CellLab | null = null;
    let skinDrift: number | null = null;
    let cover: number | null = null;
    const runner = occlusion.current;
    if (state.faces === 1 && pixels && frame) {
      grid = readCells(pixels, frame.landmarks, samplers.current.cells);
      // 가림 찾기: 가린 몫이 문턱을 넘으면 그 사진을 거르고(covered), 가린 점이 있는 칸은 그 장에서 비운다
      runner?.feed(video, frame.landmarks, now);
      const mask = runner?.latestFor(now) ?? null;
      if (mask) {
        // 가림 표의 box는 영상 원본 크기 기준이라 같은 크기로 칸 점을 옮긴다
        const cellCover = readCover(
          mask,
          { width: video.videoWidth, height: video.videoHeight },
          frame.landmarks,
          samplers.current.cells,
        );
        cover = areaCover(cellCover, areasRef.current.current);
        state.areaCover = cover;
        grid = blankCovered(grid, cellCover);
      }
      if (start) skinDrift = drift(grid, start, areasRef.current.made).size;
      state.drift = Number.isNaN(skinDrift) ? null : skinDrift;
    }
    onShot?.(now, state, grid);
    const reason = frameReason(state, makeup);
    const kept = shots.current.filter((s) => now - s.at < WINDOW.medianWindowMs);
    kept.push({ at: now, reason, grid: reason ? null : grid });
    shots.current = kept;

    let result: Measure | null = null;
    let next: GaugeDisplay;
    const usable = kept.flatMap((s) => (s.grid ? [s.grid] : []));
    if (!start) {
      next = stabilizer.current.update(now, null, "noBaseline");
    } else if (usable.length) {
      const current = framesMedian(usable);
      const whiteLinear = white ? linearOfSrgb(white) : null;
      // 조명은 천천히 바뀌어 LIGHT_EVERY_MS마다 한 번만 다시 낸다
      if (!lightCache.current || now - lightCache.current.at >= LIGHT_EVERY_MS)
        lightCache.current = { at: now, light: lightChange(current, start, areasRef.current.made) };
      const light = lightCache.current.light;
      const sides: SideInput[] = areasRef.current.areas.map(({ set, cells }) => {
        const { side, cells: count } = userSide(
          current,
          start,
          cells,
          areasRef.current.made,
          whiteLinear,
          light,
        );
        return { region: set.region, side, cells: count };
      });
      result = measure(gauge, makeup, sides);
      next = stabilizer.current.update(now, result, result.reason);
    } else {
      next = stabilizer.current.update(now, null, windowReason(kept.map((s) => s.reason)));
    }
    setDisplay((prev) => (sameDisplay(prev, next) ? prev : next));
    if (debug)
      setReading({
        measure: result,
        frame: reason,
        drift: skinDrift,
        ms: performance.now() - started,
        cover,
        occlusion: runner?.status ?? null,
      });
  });

  /**
   * 지금 하위 단계의 단계 끝 평가. end는 「다음」을 누르기 직전 사진으로 만든 끝 기준이고,
   * 시작 기준 · 영역 · 흰자는 지금 재던 값을 쓴다. 결과는 이번 실행 화면에만 쓰고 보내거나 저장하지 않는다
   */
  const evaluate = useCallback(
    (args: {
      subStepId: string;
      end: Baseline | null;
      gauge: GaugeReference | null;
      product: SelectedProduct | null;
    }): StepEvaluation => {
      const { makeup, start, white } = latest.current;
      const { areas: current, made: all } = areasRef.current;
      return evaluateStep({
        subStepId: args.subStepId,
        makeup,
        start,
        end: args.end,
        areas: current.map(({ set, cells }) => ({ region: set.region, cells })),
        gauge: args.gauge,
        white: white ? linearOfSrgb(white) : null,
        product: args.product,
        made: all,
        exclude: all,
      });
    },
    [],
  );

  return { display, reading, areas, made, evaluate };
}
