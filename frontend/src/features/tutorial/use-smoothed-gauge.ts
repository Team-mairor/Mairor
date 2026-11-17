"use client";

import { useEffect, useRef, useState } from "react";

import { LABELS, type GaugeLabel } from "@/domain/gauge/stability";

/** 화면에 보이는 막대가 새 값을 따라가는 데 걸리는 시간(ms). 몇 초에 걸쳐 출렁이는 측정 잡음을 가린다 */
export const GAUGE_SMOOTH_MS = 3000;
const TICK_MS = 100;

/** 이 막대 값부터 「비슷해요」(목표 50 아래로 넓게 잡는다) */
export const GAUGE_SIMILAR_FROM = 35;
/** 이 값을 넘으면 바로 「진해요」. 목표(50)보다 조금 위다 */
export const GAUGE_DARKER_FROM = 55;
/** 문구가 되돌아올 때만 두는 완충. 경계 근처에서 문구가 계속 바뀌지 않게 한다 */
export const GAUGE_LABEL_BACK = 3;

/**
 * 다듬은 막대 값에서 문구 번호(0 연해요 · 1 비슷해요 · 2 진해요)를 정한다. 올라갈 때는 경계를 넘는 순간 바뀌고,
 * 내려올 때는 완충만큼 더 내려가야 바뀐다. 이 경계는 화면용이고 shared/gauge 규격의 문구 경계와 따로 둔다
 */
export function gaugeLabelIndex(bar: number, prev: number | null): number {
  const back = GAUGE_SIMILAR_FROM - GAUGE_LABEL_BACK;
  if (prev === null) return bar < GAUGE_SIMILAR_FROM ? 0 : bar > GAUGE_DARKER_FROM ? 2 : 1;
  if (prev === 0) return bar >= GAUGE_SIMILAR_FROM ? (bar > GAUGE_DARKER_FROM ? 2 : 1) : 0;
  if (prev === 1) return bar > GAUGE_DARKER_FROM ? 2 : bar < back ? 0 : 1;
  return bar >= GAUGE_DARKER_FROM - GAUGE_LABEL_BACK ? 2 : bar < back ? 0 : 1;
}

export interface SmoothedGauge {
  bar: number | null;
  label: GaugeLabel | null;
}

interface State {
  bar: number | null;
  index: number | null;
}

/**
 * 게이지 막대를 천천히 따라가게 하고, 문구(연해요 · 비슷해요 · 진해요)도 그 다듬은 값에서 정한다.
 * 막대와 문구가 같은 값을 쓰므로 둘이 따로 출렁이지 않는다. 처음 값은 바로 보이고 값이 없으면(null) 바로 비운다.
 * 문구 경계는 `gaugeLabelIndex`
 */
export function useSmoothedGauge(bar: number | null): SmoothedGauge {
  const [state, setState] = useState<State>(() => ({
    bar,
    index: bar === null ? null : gaugeLabelIndex(bar, null),
  }));
  const latest = useRef(bar);
  useEffect(() => {
    latest.current = bar;
  }, [bar]);
  useEffect(() => {
    const id = setInterval(() => {
      const target = latest.current;
      setState((prev) => {
        if (target === null) return prev.bar === null ? prev : { bar: null, index: null };
        const first = prev.bar === null || prev.index === null;
        const raw = first
          ? target
          : prev.bar! + (target - prev.bar!) * (1 - Math.exp(-TICK_MS / GAUGE_SMOOTH_MS));
        const next = Math.abs(raw - target) < 0.05 ? target : raw;
        const index = gaugeLabelIndex(next, first ? null : prev.index);
        return next === prev.bar && index === prev.index ? prev : { bar: next, index };
      });
    }, TICK_MS);
    return () => clearInterval(id);
  }, []);
  return { bar: state.bar, label: state.index === null ? null : LABELS[state.index] };
}
