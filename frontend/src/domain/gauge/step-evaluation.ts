// 한 하위 단계를 마쳤을 때 한 번 내는 단계 끝 평가(덮음 · 넘침 · 진하기). AI tools/gauge/step_evaluation.py와 같은 계산이다.
// 입력은 사진이 아니라 칸 색 기준 두 개(단계 시작 · 끝)다. 값은 shared/gauge/step_evaluation.v1.json에 둔다.
// 점수 · 합격 · 단계 이동에는 쓰지 않고, 결과는 안내 문장(feedback-text.ts)으로만 바꾼다.

import type { GaugeReference } from "@/vision/guide";

import { madeCells } from "./area";
import type { Baseline } from "./baseline";
import type { CellLab } from "./cells";
import { deltaE2000 } from "./color";
import { drift, grow, lightChange } from "./light";
import {
  measure,
  MIN_AREA_CELLS,
  THIN_MAKEUPS,
  userSide,
  type MeasureReason,
  type SideInput,
  type Vec3,
} from "./measure";
import { GRID, MEASURED } from "./spec";
import { WEAK_TARGET_MIN } from "./stability";
import { measureForProduct, type SelectedProduct } from "./substitute";
import raw from "../../../../shared/gauge/step_evaluation.v1.json" with { type: "json" };

export type Side = "up" | "down" | "inner" | "outer";
export type EvaluationReason =
  "noStart" | "noEnd" | "noArea" | "thinArea" | "tooFewCells" | "covered" | "lightChanged";
export type RatioReason = MeasureReason | "weakReference" | "lightChanged" | "noProduct";

export const SIDES: readonly Side[] = raw.sides as Side[];
const DIRECTIONS: Record<string, readonly number[]> = raw.directions;
const PAINT = raw.paint;
const BAND = raw.band;
const COVERED_MAX: number = raw.coveredMax;
const DRIFT = raw.drift;
const MIN_SIDE_CELLS: number = raw.minSideCells;
/** 안내 문장 규칙이 쓰는 기준값 */
export const THRESHOLDS = raw.thresholds;

export interface SideScore {
  coverage: number | null;
  overflow: number | null;
}

/** 영역 묶음 하나(좌우 짝이면 한쪽)의 덮음 · 넘침. 못 쟀으면 값은 null이고 reason에 이유가 든다 */
export interface RegionEvaluation {
  region: string | null;
  coverage: number | null;
  overflow: number | null;
  sides: Record<Side, SideScore>;
  /** 잰 영역 칸 수와 잰 둘레 띠 칸 수 */
  cells: number;
  band: number;
  reason: "tooFewCells" | "covered" | null;
}

/** 하위 단계 하나의 단계 끝 평가. 좌우를 합친 값(weaker)과 묶음마다 값(regions)을 낸다 */
export interface StepEvaluation {
  subStepId: string;
  makeup: string;
  coverage: number | null;
  overflow: number | null;
  sides: Record<Side, SideScore>;
  /** 진하기 비율. 1이면 레퍼런스만큼 */
  ratio: number | null;
  ratioReason: RatioReason | null;
  regions: RegionEvaluation[];
  reason: EvaluationReason | null;
  drift: number | null;
}

export interface EvaluationArea {
  region: string | null;
  cells: Uint8Array;
}

export interface EvaluationInput {
  subStepId: string;
  makeup: string;
  start: Baseline | null;
  end: Baseline | null;
  areas: readonly EvaluationArea[];
  gauge?: GaugeReference | null;
  /** 맨얼굴 기준 흰자 색(선형) */
  white?: Vec3 | null;
  product?: SelectedProduct | null;
  /** 둘레 띠에서 뺄 칸(같은 단계 다른 하위 단계 영역) */
  exclude?: Uint8Array | null;
  /** 조명 재기에서 뺄 칸. 없으면 이 하위 단계 영역이다. 게이지 측정처럼 그 단계 모든 하위 단계 영역을 넘길 수 있다 */
  made?: Uint8Array | null;
}

const emptySides = (): Record<Side, SideScore> => ({
  up: { coverage: null, overflow: null },
  down: { coverage: null, overflow: null },
  inner: { coverage: null, overflow: null },
  outer: { coverage: null, overflow: null },
});

const hasColor = (lab: CellLab, k: number) =>
  !Number.isNaN(lab[k * 3]) && !Number.isNaN(lab[k * 3 + 1]) && !Number.isNaN(lab[k * 3 + 2]);

/** 바른 칸을 고를 화장 방향(Lab 단위 벡터). 레퍼런스 효과 방향, 없으면 화장 종류 기본 방향, 둘 다 없으면 null */
export function directionOf(makeup: string, gauge?: GaugeReference | null): Vec3 | null {
  const unit = (v: readonly number[]): Vec3 | null => {
    const length = Math.hypot(v[0], v[1], v[2]);
    return length > 1e-9 ? [v[0] / length, v[1] / length, v[2] / length] : null;
  };
  const delta = gauge?.effect?.delta;
  const fromGauge = delta ? unit(delta) : null;
  if (fromGauge) return fromGauge;
  return makeup in DIRECTIONS ? unit(DIRECTIONS[makeup]) : null;
}

/** 바른 칸 문턱(Lab 길이). 레퍼런스 효과 길이의 share배이고 floor보다 작지 않다 */
export function paintLift(gauge?: GaugeReference | null): number {
  const delta = gauge?.effect?.delta;
  if (!delta) return PAINT.floor;
  return Math.max(PAINT.floor, PAINT.share * Math.hypot(delta[0], delta[1], delta[2]));
}

/** 칸마다 (바른 칸인지, 잴 수 있는 칸인지). 조명 바뀜을 뺀 끝 색과 시작 색을 견준다 */
export function paintedCells(
  start: Baseline,
  end: Baseline,
  made: Uint8Array | null,
  direction: Vec3 | null,
  lift: number,
  light: CellLab = lightChange(end.lab, start, made),
): { painted: Uint8Array; valid: Uint8Array } {
  const painted = new Uint8Array(GRID * GRID);
  const valid = new Uint8Array(GRID * GRID);
  for (let k = 0; k < GRID * GRID; k++) {
    if (!start.cells[k] || !end.cells[k] || !hasColor(end.lab, k)) continue;
    valid[k] = 1;
    const now = [0, 1, 2].map((ch) => end.lab[k * 3 + ch] - light[k * 3 + ch]);
    if (direction) {
      const moved = [0, 1, 2].reduce(
        (sum, ch) => sum + (now[ch] - start.lab[k * 3 + ch]) * direction[ch],
        0,
      );
      painted[k] = moved >= lift ? 1 : 0;
    } else {
      const size = deltaE2000(
        now[0],
        now[1],
        now[2],
        start.lab[k * 3],
        start.lab[k * 3 + 1],
        start.lab[k * 3 + 2],
      );
      painted[k] = size >= PAINT.deltaFallback ? 1 : 0;
    }
  }
  return { painted, valid };
}

/** 영역 둘레 띠 칸. 영역에서 gap칸 띄운 뒤 width칸 두께이고 재는 칸만 쓴다 */
export function bandCells(
  area: Uint8Array,
  exclude: Uint8Array | null = null,
  width: number = BAND.width,
  gap: number = BAND.gap,
): Uint8Array {
  const outer = grow(area, gap + width);
  const inner = gap > 0 ? grow(area, gap) : area;
  const out = new Uint8Array(GRID * GRID);
  for (let k = 0; k < out.length; k++)
    out[k] = outer[k] && !inner[k] && MEASURED[k] && !exclude?.[k] ? 1 : 0;
  return out;
}

/** 위(0) · 아래(1) · 안쪽(2) · 바깥쪽(3) 번호. 위아래 거리가 더 크면 위아래, 아니면 가운데 선 쪽 */
const sideNumber = (dy: number, dx: number) =>
  Math.abs(dy) >= Math.abs(dx) ? (dy < 0 ? 0 : 1) : dx < 0 ? 2 : 3;

const cellsOf = (mask: Uint8Array) => {
  const out: number[] = [];
  for (let k = 0; k < mask.length; k++) if (mask[k]) out.push(k);
  return out;
};

/** 영역 칸을 방향 번호로 나눈다(영역 밖은 -1). 영역 가운데에서 위아래 · 가운데 선에서 멀어진 거리를 영역 반 크기로 나눠 큰 쪽이다 */
export function areaSides(area: Uint8Array): Int8Array {
  const out = new Int8Array(GRID * GRID).fill(-1);
  const keys = cellsOf(area);
  if (!keys.length) return out;
  const middle = (GRID - 1) / 2;
  const rows = keys.map((k) => Math.floor(k / GRID));
  const away = keys.map((k) => Math.abs((k % GRID) - middle));
  const mean = (v: number[]) => v.reduce((a, b) => a + b, 0) / v.length;
  const tall = Math.max((Math.max(...rows) - Math.min(...rows) + 1) / 2, 1);
  const wide = Math.max((Math.max(...away) - Math.min(...away) + 1) / 2, 1);
  const rowMean = mean(rows);
  const awayMean = mean(away);
  keys.forEach((k, i) => {
    out[k] = sideNumber((rows[i] - rowMean) / tall, (away[i] - awayMean) / wide);
  });
  return out;
}

/** 둘레 띠 칸을 방향 번호로 나눈다(띠 밖은 -1). 가장 가까운 영역 칸에서 그 칸까지 간 방향이다 */
export function bandSides(area: Uint8Array, band: Uint8Array): Int8Array {
  const out = new Int8Array(GRID * GRID).fill(-1);
  const inside = cellsOf(area);
  if (!inside.length) return out;
  const middle = (GRID - 1) / 2;
  for (const k of cellsOf(band)) {
    const row = Math.floor(k / GRID);
    const col = k % GRID;
    let best = Infinity;
    let near = inside[0];
    for (const a of inside) {
      const d = (Math.floor(a / GRID) - row) ** 2 + ((a % GRID) - col) ** 2;
      if (d < best) {
        best = d;
        near = a;
      }
    }
    const dy = row - Math.floor(near / GRID);
    const dx = Math.abs(col - middle) - Math.abs((near % GRID) - middle);
    out[k] = sideNumber(dy, dx);
  }
  return out;
}

/** mask 안 칸 중 바른 칸 몫. 칸이 minSideCells보다 적으면 null */
function share(painted: Uint8Array, mask: Uint8Array | Int8Array, index?: number): number | null {
  let count = 0;
  let hit = 0;
  for (let k = 0; k < painted.length; k++) {
    if (index === undefined ? !mask[k] : mask[k] !== index) continue;
    count++;
    if (painted[k]) hit++;
  }
  return count < MIN_SIDE_CELLS ? null : hit / count;
}

/** 영역 묶음 하나의 덮음 · 넘침과 방향별 값 */
export function scoreRegion(
  region: string | null,
  areaCells: Uint8Array,
  painted: Uint8Array,
  valid: Uint8Array,
  exclude: Uint8Array | null,
): RegionEvaluation {
  const area = new Uint8Array(GRID * GRID);
  for (let k = 0; k < area.length; k++) area[k] = areaCells[k] && MEASURED[k] ? 1 : 0;
  const cells = area.reduce((sum, v) => sum + v, 0);
  if (cells < MIN_AREA_CELLS)
    return {
      region,
      coverage: null,
      overflow: null,
      sides: emptySides(),
      cells,
      band: 0,
      reason: "tooFewCells",
    };
  const seen = area.map((v, k) => (v && valid[k] ? 1 : 0));
  const seenCount = seen.reduce((sum, v) => sum + v, 0);
  if (1 - seenCount / cells > COVERED_MAX)
    return {
      region,
      coverage: null,
      overflow: null,
      sides: emptySides(),
      cells: seenCount,
      band: 0,
      reason: "covered",
    };
  const band = bandCells(area, exclude).map((v, k) => (v && valid[k] ? 1 : 0));
  const inside = areaSides(seen);
  const around = bandSides(area, band);
  const sides = emptySides();
  SIDES.forEach((side, index) => {
    sides[side] = {
      coverage: share(painted, inside, index),
      overflow: share(painted, around, index),
    };
  });
  return {
    region,
    coverage: share(painted, seen),
    overflow: share(painted, band),
    sides,
    cells: seenCount,
    band: band.reduce((sum, v) => sum + v, 0),
    reason: null,
  };
}

/** 값이 있는 것 가운데 low면 가장 작은 값, 아니면 가장 큰 값 */
const pick = (values: (number | null)[], low: boolean) => {
  const some = values.filter((v): v is number => v !== null);
  if (!some.length) return null;
  return low ? Math.min(...some) : Math.max(...some);
};

/** 좌우 묶음 값을 하나로 합친다. 덮음은 가장 적은 쪽, 넘침은 가장 많은 쪽이다(방향별도 같다) */
export function combineRegions(regions: readonly RegionEvaluation[]) {
  const valid = regions.filter((r) => r.coverage !== null);
  if (!valid.length) return { coverage: null, overflow: null, sides: emptySides() };
  const sides = emptySides();
  for (const side of SIDES)
    sides[side] = {
      coverage: pick(
        valid.map((r) => r.sides[side].coverage),
        true,
      ),
      overflow: pick(
        valid.map((r) => r.sides[side].overflow),
        false,
      ),
    };
  return {
    coverage: pick(
      valid.map((r) => r.coverage),
      true,
    ),
    overflow: pick(
      valid.map((r) => r.overflow),
      false,
    ),
    sides,
  };
}

function ratioOf(
  input: EvaluationInput & { start: Baseline; end: Baseline },
  made: Uint8Array,
  light: CellLab,
): { ratio: number | null; reason: RatioReason | null } {
  const { start, end, areas, makeup, gauge = null, white = null, product = null } = input;
  const sides: SideInput[] = areas.map(({ region, cells }) => ({
    region,
    ...userSide(end.lab, start, cells, made, white, light),
  }));
  let out;
  if (product) {
    const result = measureForProduct(gauge, makeup, sides, product);
    if (!result.measure) return { ratio: null, reason: result.rule.hideReason ?? "noProduct" };
    out = result.measure;
  } else {
    out = measure(gauge, makeup, sides);
  }
  if (out.ratio === null) return { ratio: null, reason: out.reason };
  if (out.target !== null && out.target < WEAK_TARGET_MIN)
    return { ratio: null, reason: "weakReference" };
  return { ratio: out.ratio, reason: null };
}

/** 하위 단계 하나의 단계 끝 평가 */
export function evaluateStep(input: EvaluationInput): StepEvaluation {
  const { subStepId, makeup, start, end, areas, gauge = null, exclude = null } = input;
  const none = (reason: EvaluationReason, moved: number | null = null): StepEvaluation => ({
    subStepId,
    makeup,
    coverage: null,
    overflow: null,
    sides: emptySides(),
    ratio: null,
    ratioReason: null,
    regions: [],
    reason,
    drift: moved,
  });
  if (!start || !end) return none(start ? "noEnd" : "noStart");
  if (!areas.length) return none("noArea");
  if (THIN_MAKEUPS.includes(makeup)) return none("thinArea");

  const made = input.made ?? madeCells(areas.map((a) => a.cells));
  const size = drift(end.lab, start, made).size;
  const moved = Number.isNaN(size) ? null : size;
  if (moved !== null && moved > DRIFT.allMax) return none("lightChanged", moved);

  // 조명 바뀜은 칸마다 흐려 무거우므로 바른 칸 고르기와 진하기가 한 번 낸 값을 같이 쓴다
  const light = lightChange(end.lab, start, made);
  const { painted, valid } = paintedCells(
    start,
    end,
    made,
    directionOf(makeup, gauge),
    paintLift(gauge),
    light,
  );
  const others = exclude ? made.map((v, k) => (v || exclude[k] ? 1 : 0)) : made;
  const regions = areas.map(({ region, cells }) =>
    scoreRegion(
      region,
      cells,
      painted,
      valid,
      others.map((v, k) => (v && !cells[k] ? 1 : 0)),
    ),
  );
  const combined = combineRegions(regions);
  if (combined.coverage === null) {
    const reason = regions.find((r) => r.reason)?.reason ?? "tooFewCells";
    return { ...none(reason, moved), regions };
  }
  let { ratio, reason: ratioReason } = ratioOf({ ...input, start, end }, made, light);
  if (ratio !== null && moved !== null && moved > DRIFT.ratioMax) {
    ratio = null;
    ratioReason = "lightChanged";
  }
  return {
    subStepId,
    makeup,
    ...combined,
    ratio,
    ratioReason,
    regions,
    reason: null,
    drift: moved,
  };
}
