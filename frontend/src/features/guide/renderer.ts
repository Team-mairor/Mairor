import {
  HoldVisibility,
  isGuideVisible,
  isRegionInView,
  MIN_IN_FRAME_RATIO,
  type FaceFrame,
  type GuideShape,
  type Point,
} from "@/features/face";
import { resolveAnchor, type FaceMesh } from "@/features/overlay";

import type { GuideStep } from "./types";

type Px = { x: number; y: number };

/** 정규화 좌표를 화면 픽셀로 옮기는 방법. 카메라 화면과 하프미러는 계산이 달라 밖에서 넘긴다 */
export interface Projection {
  toPx: (p: Point) => Px;
  /** IOD = 1 단위가 화면에서 몇 픽셀인지 */
  unit: number;
}

// 하프미러(검은 배경) 위에 흰 선만 떠 있게 그린다. 화면이 밝은 곳은 거울에 비친 얼굴이 흐려지므로
// 영역을 채우거나 띠를 깔지 않는다. 크기는 IOD 기준이고, 멀어져도 최소 픽셀은 지킨다.
/** 가이드 색 (R, G, B). 하프미러에 올려 보고 바꿀 때는 이 값만 고친다 */
const INK = "255, 255, 255";

const STYLE = {
  color: `rgba(${INK}, 0.98)`,
  // 선 둘레의 옅은 흰 빛. 흐림 필터는 저사양 기기에서 무거워 넓고 옅은 선 두 겹으로 퍼지게 한다
  glow: [
    { color: `rgba(${INK}, 0.08)`, extra: 10 },
    { color: `rgba(${INK}, 0.16)`, extra: 4 },
  ],
  /** 점선의 점 지름, 점 사이 간격(점 지름 대비) */
  dot: { size: 0.032, min: 3, gap: 0.8 },
  /** 실선(화살표) 두께 */
  line: { size: 0.035, min: 3 },
  /** 경로의 점선이 흐르는 속도 (점 지름/초). 방향만 알 수 있게 느리게 */
  flow: 0.8,
  /** 화살촉 크기 */
  arrowHead: 0.14,
  /** 시작점 반지름 */
  point: { size: 0.05, min: 5 },
  /** 붓 자국 가운데 최소 두께 (px). 두께는 도형의 width를 쓴다 */
  brushMin: 1.2,
};

/**
 * 정확하지 않은 가이드는 보여주지 않는다. 공용 규칙(isGuideVisible)대로 추적이 안정적일 때만 보이고,
 * 단계 부위가 모두 가려지면 숨긴다. 깜빡임(hold) 때의 유지는 GuideRenderer가 직전 판정으로 처리한다.
 */
export function isStepVisible(
  step: GuideStep,
  frame: FaceFrame | null,
  minInFrameRatio = MIN_IN_FRAME_RATIO,
): boolean {
  if (!frame || !isGuideVisible(frame)) return false;
  if (step.regions.length === 0) return true;
  // 얼굴 전체(faceOval)는 가까이 가면 늘 잘리고, 화면 밖 부분은 그릴 때 알아서 빠지므로 숨기지 않는다.
  return step.regions.some(
    (region) => region === "faceOval" || isRegionInView(frame, region, minInFrameRatio),
  );
}

/**
 * 얼굴 위에 튜토리얼 가이드를 그린다. 도형마다 모양을 달리해 한 단계 안에서 겹쳐도 구분되게 한다.
 * - 영역(polygon): 둥근 점선 테두리 (멈춤)
 * - 경로(polyline): 진행 방향으로 천천히 흐르는 점선. 점 지름은 도형의 width와 기본값 중 큰 쪽
 * - 붓 자국(polyline, brush): 양 끝이 가는 결 방향 자국 (눈썹 결·속눈썹)
 * - 방향(arrow): 굵은 실선과 화살촉
 * - 시작점(point): 속이 찬 점
 */
export class GuideRenderer {
  private readonly ctx: CanvasRenderingContext2D;
  private dpr = 1;
  // 직전에 보이던 가이드만 깜빡임(hold) 동안 유지한다.
  private readonly visibility = new HoldVisibility();
  private stepId: string | null = null;

  constructor(private readonly canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("캔버스 2D를 쓸 수 없습니다");
    this.ctx = ctx;
  }

  resize(width: number, height: number, dpr: number) {
    this.dpr = dpr;
    this.canvas.width = Math.round(width * dpr);
    this.canvas.height = Math.round(height * dpr);
  }

  clear() {
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  render(options: {
    frame: FaceFrame | null;
    step: GuideStep | null;
    mesh: FaceMesh | null;
    projection: Projection | null;
    /** 점선 흐름에 쓰는 시각 (ms) */
    now: number;
  }) {
    const { frame, step, mesh, projection, now } = options;
    this.clear();
    // 단계가 바뀌면 이전 단계의 판정으로 새 단계 가이드를 그리지 않는다.
    if ((step?.stepId ?? null) !== this.stepId) {
      this.stepId = step?.stepId ?? null;
      this.visibility.reset();
    }
    const visible = !!step && this.visibility.update(frame, () => isStepVisible(step, frame));
    if (!frame || !step || !mesh || !projection || !visible) return;

    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    const at = (anchor: Parameters<typeof resolveAnchor>[0]) =>
      projection.toPx(resolveAnchor(anchor, mesh, frame.landmarks));
    const dot = sized(projection.unit, STYLE.dot);
    const dashOffset = -(now / 1000) * STYLE.flow * dot * (1 + STYLE.dot.gap);

    // 붓 자국은 다른 도형보다 먼저 깔아 시작점·화살표가 위에 보이게 한다.
    const ordered = [...step.guides].sort((a, b) => Number(isBrush(b)) - Number(isBrush(a)));
    for (const guide of ordered) {
      this.drawGuide(guide, at, projection.unit, dashOffset);
    }
  }

  private drawGuide(
    guide: GuideShape,
    at: (anchor: Parameters<typeof resolveAnchor>[0]) => Px,
    unit: number,
    dashOffset: number,
  ) {
    const ctx = this.ctx;
    const dot = sized(unit, STYLE.dot);
    switch (guide.type) {
      case "polygon": {
        // 바를 영역: 둥근 점선 테두리. 점을 곡선으로 이어 각지지 않게 하고, 방향이 없으므로 흐르지 않게 한다
        const points = guide.outline.map(at);
        if (points.length < 3) return;
        traceSmooth(ctx, points, true);
        this.dotted(dot, 0);
        return;
      }
      case "polyline": {
        const points = guide.path.map(at);
        if (points.length < 2) return;
        if (guide.brush) {
          this.brushStroke(points, Math.max(STYLE.brushMin, guide.width * unit));
          return;
        }
        // 그릴 선: 점선이 진행 방향으로 천천히 흐름
        traceSmooth(ctx, points, false);
        this.dotted(Math.max(dot, guide.width * unit), dashOffset);
        return;
      }
      case "arrow": {
        // 바르는 방향: 영역 테두리(점선)와 헷갈리지 않게 실선
        const from = at(guide.from);
        const to = at(guide.to);
        const width = sized(unit, STYLE.line);
        tracePath(ctx, [from, to], false);
        this.solid(width);
        const head = arrowHead(from, to, Math.max(width * 3, STYLE.arrowHead * unit));
        if (!head) return;
        tracePath(ctx, head, false);
        this.solid(width);
        return;
      }
      case "point": {
        // 시작점
        const p = at(guide.at);
        ctx.beginPath();
        ctx.arc(p.x, p.y, sized(unit, STYLE.point), 0, Math.PI * 2);
        this.halo(0);
        ctx.fillStyle = STYLE.color;
        ctx.fill();
        return;
      }
    }
  }

  /** 지금 경로를 둥근 점이 이어진 점선으로 긋는다 (흰 빛 + 흰 점). */
  private dotted(dot: number, dashOffset: number) {
    const ctx = this.ctx;
    // 길이 0인 대시에 둥근 끝을 붙이면 점이 된다.
    ctx.setLineDash([0, dot * (1 + STYLE.dot.gap)]);
    ctx.lineDashOffset = dashOffset;
    this.halo(dot);
    ctx.strokeStyle = STYLE.color;
    ctx.lineWidth = dot;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineDashOffset = 0;
  }

  /** 지금 경로를 실선으로 긋는다 (흰 빛 + 흰 선). */
  private solid(width: number) {
    const ctx = this.ctx;
    ctx.setLineDash([]);
    this.halo(width);
    ctx.strokeStyle = STYLE.color;
    ctx.lineWidth = width;
    ctx.stroke();
  }

  /** 지금 경로 둘레에 옅은 흰 빛을 깐다. width는 그 위에 그릴 선 두께 */
  private halo(width: number) {
    const ctx = this.ctx;
    for (const g of STYLE.glow) {
      ctx.strokeStyle = g.color;
      ctx.lineWidth = width + g.extra;
      ctx.stroke();
    }
  }

  /** 붓 자국: 뿌리는 굵고 끝으로 갈수록 가는 모양을 한 번에 채운다. */
  private brushStroke(path: Px[], width: number) {
    const ctx = this.ctx;
    const samples = 16;
    const left: Px[] = [];
    const right: Px[] = [];
    for (let k = 0; k <= samples; k++) {
      const u = k / samples;
      const p = pointAlong(path, u);
      const q = pointAlong(path, Math.min(1, u + 0.02));
      const o = pointAlong(path, Math.max(0, u - 0.02));
      const len = Math.hypot(q.x - o.x, q.y - o.y) || 1;
      const half = (width / 2) * (0.35 + 0.65 * (1 - u));
      const nx = (-(q.y - o.y) / len) * half;
      const ny = ((q.x - o.x) / len) * half;
      left.push({ x: p.x + nx, y: p.y + ny });
      right.push({ x: p.x - nx, y: p.y - ny });
    }
    tracePath(ctx, [...left, ...right.reverse()], true);
    // 가는 결이 빛에 번져 뭉개지지 않게 붓 자국은 흰색만 칠한다
    ctx.fillStyle = STYLE.color;
    ctx.fill();
  }
}

/** IOD 기준 크기를 픽셀로. 멀어져도 최소 픽셀은 지킨다 */
const sized = (unit: number, s: { size: number; min: number }) => Math.max(s.min, s.size * unit);

const isBrush = (guide: GuideShape) => guide.type === "polyline" && !!guide.brush;

function tracePath(ctx: CanvasRenderingContext2D, points: Px[], close: boolean) {
  ctx.beginPath();
  points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
  if (close) ctx.closePath();
}

/** 점을 모두 지나는 곡선(Catmull-Rom)으로 이어 각지지 않게 그린다. 영역이 정의한 점보다 줄어들지 않는다. */
function traceSmooth(ctx: CanvasRenderingContext2D, points: Px[], close: boolean) {
  const n = points.length;
  const pt = (i: number) =>
    close ? points[((i % n) + n) % n] : points[Math.max(0, Math.min(n - 1, i))];
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 0; i < (close ? n : n - 1); i++) {
    const [p0, p1, p2, p3] = [pt(i - 1), pt(i), pt(i + 1), pt(i + 2)];
    ctx.bezierCurveTo(
      p1.x + (p2.x - p0.x) / 6,
      p1.y + (p2.y - p0.y) / 6,
      p2.x - (p3.x - p1.x) / 6,
      p2.y - (p3.y - p1.y) / 6,
      p2.x,
      p2.y,
    );
  }
  if (close) ctx.closePath();
}

/** 꺾은선을 따라 길이 비율 t(0~1)만큼 간 점 */
function pointAlong(points: Px[], t: number): Px {
  const lengths = points.slice(1).map((p, i) => Math.hypot(p.x - points[i].x, p.y - points[i].y));
  let left = Math.min(1, Math.max(0, t)) * lengths.reduce((a, b) => a + b, 0);
  for (let i = 0; i < lengths.length; i++) {
    if (left <= lengths[i] || i === lengths.length - 1) {
      const r = lengths[i] ? Math.min(1, left / lengths[i]) : 0;
      return {
        x: points[i].x + (points[i + 1].x - points[i].x) * r,
        y: points[i].y + (points[i + 1].y - points[i].y) * r,
      };
    }
    left -= lengths[i];
  }
  return points[0];
}

/** 끝점에서 뒤로 벌어진 화살촉 두 변 [왼쪽 끝, 꼭짓점, 오른쪽 끝] */
function arrowHead(from: Px, to: Px, size: number): Px[] | null {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy);
  if (len < 1) return null;
  const ux = dx / len;
  const uy = dy / len;
  const back = { x: to.x - ux * size, y: to.y - uy * size };
  const half = size * 0.6;
  return [
    { x: back.x - uy * half, y: back.y + ux * half },
    to,
    { x: back.x + uy * half, y: back.y - ux * half },
  ];
}
