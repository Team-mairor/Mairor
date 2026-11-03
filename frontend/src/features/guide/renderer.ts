import {
  HoldVisibility,
  isGuideVisible,
  isRegionInView,
  MIN_IN_FRAME_RATIO,
  REGIONS,
  type FaceFrame,
  type GuideShape,
  type Point,
  type RegionName,
} from "@/features/face";
import { resolveAnchor, type FaceMesh } from "@/features/overlay";

import { isThinArea } from "./thin-area";
import type { GuideItem, GuideStep } from "./types";

type Px = { x: number; y: number };

/** 정규화 좌표를 화면 픽셀로 옮기는 방법. 카메라 화면과 하프미러는 계산이 달라 밖에서 넘긴다 */
export interface Projection {
  toPx: (p: Point) => Px;
  /** IOD = 1 단위가 화면에서 몇 픽셀인지 */
  unit: number;
}

// 어두운 배경 위에 선만 떠 있게 그린다. 화면이 밝은 곳은 거울에 비친 얼굴이 흐려지므로
// 영역을 채우거나 띠를 깔지 않는다. 크기는 IOD 기준이고, 멀어져도 최소 픽셀은 지킨다.
// 어디에 바를지(영역)와 어떻게 움직일지(경로·화살표·시작점·붓 자국)를 두 가지 색으로 나눠 한눈에 구분되게 한다.
/** 가이드 색 (R, G, B). 하프미러에 올려 보고 바꿀 때는 이 값만 고친다 */
const AREA_INK = "255, 72, 164";
const MOTION_INK = "214, 247, 77";
/** 영상 대신 깔아 두는 얼굴 윤곽 색 */
const FACE_INK = "255, 255, 255";
const FACE_PARTS: RegionName[] = [
  "faceOval",
  "rightBrow",
  "leftBrow",
  "rightEye",
  "leftEye",
  "lipsOuter",
];
/** 코끝 점 번호. 코는 부위(regions.v1.json)에 없어 직접 쓴다 */
const NOSE_TIP = 1;

const STYLE = {
  alpha: 0.98,
  // 선 둘레의 옅은 빛. 흐림 필터는 저사양 기기에서 무거워 넓고 옅은 선 두 겹으로 퍼지게 한다
  glow: [
    { alpha: 0.1, extra: 12 },
    { alpha: 0.22, extra: 5 },
  ],
  /** 얼굴 윤곽 선의 진하기와 두께. 가이드(점선 0.032·실선 0.035)보다는 가늘게 둬 가이드가 먼저 보이게 한다 */
  face: { alpha: 0.5, size: 0.02, min: 2.5 },
  /** 점선의 점 지름, 점 사이 간격(점 지름 대비) */
  dot: { size: 0.032, min: 3, gap: 0.8 },
  /** 얇은 띠 영역(isThinArea)의 점 지름(점 지름 대비). 멀어져도 dot.min은 지킨다 */
  thinDot: { scale: 0.5 },
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
 * - 영역(polygon): 둥근 점선 테두리 (멈춤). 아이라인처럼 얇은 띠는 작은 점.
 *   빼는 부위(exclude)는 안쪽을 지우고 그 테두리를 구멍으로 그린다
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
    /** 영상 대신 옅은 얼굴 윤곽을 깐다 */
    face?: boolean;
  }) {
    const { frame, step, mesh, projection, now, face = false } = options;
    this.clear();
    // 단계가 바뀌면 이전 단계의 판정으로 새 단계 가이드를 그리지 않는다.
    if ((step?.stepId ?? null) !== this.stepId) {
      this.stepId = step?.stepId ?? null;
      this.visibility.reset();
    }
    const visible = !!step && this.visibility.update(frame, () => isStepVisible(step, frame));
    if (!frame || !projection) return;

    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    // 윤곽은 단계에 가이드가 없어도(영역 실패 등) 그려 가운데가 비지 않게 한다. 숨길지는 부르는 쪽이 face로 정한다
    if (face && isGuideVisible(frame)) this.drawFace(frame, projection);
    if (!step || !mesh || !visible) return;

    const at = (anchor: Parameters<typeof resolveAnchor>[0]) =>
      projection.toPx(resolveAnchor(anchor, mesh, frame.landmarks));
    const dot = sized(projection.unit, STYLE.dot);
    const dashOffset = -(now / 1000) * STYLE.flow * dot * (1 + STYLE.dot.gap);

    // 빼는 부위 테두리는 이번 화면에서 부위마다 한 번만 픽셀로 바꾼다
    const holePx = new Map<RegionName, Px[]>();
    const holeOf = (name: RegionName) => {
      let px = holePx.get(name);
      if (!px) {
        px = REGIONS[name].indices.map((k) => projection.toPx(frame.landmarks[k]));
        holePx.set(name, px);
      }
      return px;
    };

    // 붓 자국은 다른 도형보다 먼저 깔아 시작점·화살표가 위에 보이게 한다.
    const ordered = [...step.guides].sort((a, b) => Number(isBrush(b)) - Number(isBrush(a)));
    const yaw = frame.pose.yaw;
    const toPx = (i: number) => projection.toPx(frame.landmarks[i]);
    for (const guide of ordered) {
      const areaDot = isThinArea(guide, mesh)
        ? Math.max(STYLE.dot.min, dot * STYLE.thinDot.scale)
        : dot;
      const draw = () => {
        if (guide.type === "polygon" && guide.exclude?.length)
          this.drawPolygonWithHoles(guide, guide.exclude.map(holeOf), at, areaDot);
        else this.drawGuide(guide, at, projection.unit, dashOffset, areaDot);
      };
      // 얼굴 윤곽처럼 양쪽 끝까지 걸친 도형은 먼 쪽 절반만 옅게 한다
      if (spans(guide, mesh)) {
        this.drawHalves(draw, toPx(MIDLINE[0]), toPx(MIDLINE[1]), toPx(LEFT_EDGE), yaw);
        continue;
      }
      const alpha = turnFade(guide, mesh, yaw);
      if (alpha <= 0) continue;
      ctx.globalAlpha = alpha;
      draw();
    }
    ctx.globalAlpha = 1;
  }

  /** 얼굴 윤곽·눈·눈썹·입술 테두리를 옅게 그어, 가이드가 얼굴 어디에 있는지 알 수 있게 한다 */
  private drawFace(frame: FaceFrame, projection: Projection) {
    const ctx = this.ctx;
    const ink = `rgba(${FACE_INK}, ${STYLE.face.alpha})`;
    const width = sized(projection.unit, STYLE.face);
    ctx.beginPath();
    for (const part of FACE_PARTS) {
      traceSmooth(
        ctx,
        REGIONS[part].indices.map((k) => projection.toPx(frame.landmarks[k])),
        true,
        false,
      );
    }
    ctx.setLineDash([]);
    ctx.strokeStyle = ink;
    ctx.lineWidth = width;
    ctx.stroke();
    // 코는 코끝 점만 찍는다. 콧방울은 볼과 색 차이가 적어 점이 실제 코 폭과 어긋나 선으로 그리지 않는다
    const tip = projection.toPx(frame.landmarks[NOSE_TIP]);
    ctx.beginPath();
    ctx.arc(tip.x, tip.y, width * 1.5, 0, Math.PI * 2);
    ctx.fillStyle = ink;
    ctx.fill();
  }

  /** 얼굴 가운데 선(top → bottom)으로 나눠 반쪽마다 고개 각도에 맞는 진하기로 그린다 */
  private drawHalves(draw: () => void, top: Px, bottom: Px, leftEdge: Px, yaw: number) {
    const ctx = this.ctx;
    const len = Math.hypot(bottom.x - top.x, bottom.y - top.y) || 1;
    const d = { x: (bottom.x - top.x) / len, y: (bottom.y - top.y) / len };
    // 본인 기준 왼쪽 반쪽을 향하는 법선
    let n = { x: -d.y, y: d.x };
    if ((leftEdge.x - top.x) * n.x + (leftEdge.y - top.y) * n.y < 0) n = { x: d.y, y: -d.x };
    const far = HALF_PLANE;
    for (const side of [1, -1]) {
      const alpha = 1 - smoothstep(AWAY_FADE.side[0], AWAY_FADE.side[1], side * yaw);
      if (alpha <= 0) continue;
      const a = { x: top.x - d.x * far, y: top.y - d.y * far };
      const b = { x: bottom.x + d.x * far, y: bottom.y + d.y * far };
      const o = { x: n.x * side * far, y: n.y * side * far };
      ctx.save();
      tracePath(ctx, [a, b, { x: b.x + o.x, y: b.y + o.y }, { x: a.x + o.x, y: a.y + o.y }], true);
      ctx.clip();
      ctx.globalAlpha = alpha;
      draw();
      ctx.restore();
    }
  }

  /** 영역 테두리에서 빼는 부위 안쪽을 지우고, 영역 안에 걸친 빼는 부위 테두리를 구멍으로 그린다 */
  private drawPolygonWithHoles(
    guide: Extract<GuideItem, { type: "polygon" }>,
    holes: Px[][],
    at: (anchor: Parameters<typeof resolveAnchor>[0]) => Px,
    dot: number,
  ) {
    const ctx = this.ctx;
    const points = guide.outline.map(at);
    if (points.length < 3) return;
    // 입을 다물 때처럼 거의 닫힌 구멍은 빼지 않는다
    const minHole = Math.abs(polygonArea(points)) * MIN_HOLE_AREA;
    holes = holes.filter((hole) => Math.abs(polygonArea(hole)) >= minHole);
    if (!holes.length) {
      traceSmooth(ctx, points, true);
      this.dotted(dot, 0, AREA_INK);
      return;
    }
    const { width, height } = this.canvas;
    // 영역 테두리: 빼는 부위 밖에서만. 구멍마다 따로 잘라 겹친 구멍이 서로 지워지지 않게 한다
    ctx.save();
    for (const hole of holes) {
      ctx.beginPath();
      ctx.rect(0, 0, width, height);
      traceSmooth(ctx, hole, true, false);
      ctx.clip("evenodd");
    }
    traceSmooth(ctx, points, true);
    this.dotted(dot, 0, AREA_INK);
    ctx.restore();
    // 구멍 테두리: 영역 안에서만, 한 경로로 모아 한 번에 긋는다
    ctx.save();
    traceSmooth(ctx, points, true);
    ctx.clip();
    ctx.beginPath();
    for (const hole of holes) traceSmooth(ctx, hole, true, false);
    this.dotted(dot, 0, AREA_INK);
    ctx.restore();
  }

  private drawGuide(
    guide: GuideShape,
    at: (anchor: Parameters<typeof resolveAnchor>[0]) => Px,
    unit: number,
    dashOffset: number,
    areaDot: number,
  ) {
    const ctx = this.ctx;
    const dot = sized(unit, STYLE.dot);
    switch (guide.type) {
      case "polygon": {
        // 바를 영역: 둥근 점선 테두리. 점을 곡선으로 이어 각지지 않게 하고, 방향이 없으므로 흐르지 않게 한다
        const points = guide.outline.map(at);
        if (points.length < 3) return;
        traceSmooth(ctx, points, true);
        this.dotted(areaDot, 0, AREA_INK);
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
        this.dotted(Math.max(dot, guide.width * unit), dashOffset, MOTION_INK);
        return;
      }
      case "arrow": {
        // 바르는 방향: 영역 테두리(점선)와 헷갈리지 않게 실선
        const from = at(guide.from);
        const to = at(guide.to);
        const width = sized(unit, STYLE.line);
        tracePath(ctx, [from, to], false);
        this.solid(width, MOTION_INK);
        const head = arrowHead(from, to, Math.max(width * 3, STYLE.arrowHead * unit));
        if (!head) return;
        tracePath(ctx, head, false);
        this.solid(width, MOTION_INK);
        return;
      }
      case "point": {
        // 시작점
        const p = at(guide.at);
        ctx.beginPath();
        ctx.arc(p.x, p.y, sized(unit, STYLE.point), 0, Math.PI * 2);
        this.halo(0, MOTION_INK);
        ctx.fillStyle = `rgba(${MOTION_INK}, ${STYLE.alpha})`;
        ctx.fill();
        return;
      }
    }
  }

  /** 지금 경로를 둥근 점이 이어진 점선으로 긋는다 (같은 색 빛 + 점). ink는 R, G, B */
  private dotted(dot: number, dashOffset: number, ink: string) {
    const ctx = this.ctx;
    // 길이 0인 대시에 둥근 끝을 붙이면 점이 된다.
    ctx.setLineDash([0, dot * (1 + STYLE.dot.gap)]);
    ctx.lineDashOffset = dashOffset;
    this.halo(dot, ink);
    ctx.strokeStyle = `rgba(${ink}, ${STYLE.alpha})`;
    ctx.lineWidth = dot;
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineDashOffset = 0;
  }

  /** 지금 경로를 실선으로 긋는다 (같은 색 빛 + 선). */
  private solid(width: number, ink: string) {
    const ctx = this.ctx;
    ctx.setLineDash([]);
    this.halo(width, ink);
    ctx.strokeStyle = `rgba(${ink}, ${STYLE.alpha})`;
    ctx.lineWidth = width;
    ctx.stroke();
  }

  /** 지금 경로 둘레에 옅은 빛을 깐다. width는 그 위에 그릴 선 두께 */
  private halo(width: number, ink: string) {
    const ctx = this.ctx;
    for (const g of STYLE.glow) {
      ctx.strokeStyle = `rgba(${ink}, ${g.alpha})`;
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
    // 가는 결이 빛에 번져 뭉개지지 않게 붓 자국은 빛 없이 칠한다
    ctx.fillStyle = `rgba(${MOTION_INK}, ${STYLE.alpha})`;
    ctx.fill();
  }
}

// 고개를 돌리면 먼 쪽 점은 얼굴 뒤로 넘어가 어긋나므로, 이 각도(라디안) 사이에서 옅어지다 숨긴다
const AWAY_FADE = { side: [0.15, 0.35], center: [0.4, 0.6] } as const;
/** 얼굴 가운데 선(이마 위, 턱 끝)과 본인 기준 왼쪽 끝 랜드마크 */
const MIDLINE = [10, 152] as const;
const LEFT_EDGE = 454;
/** 반쪽 영역을 화면 밖까지 덮는 길이 (px) */
const HALF_PLANE = 10000;

function anchorsOf(guide: GuideShape) {
  switch (guide.type) {
    case "point":
      return [guide.at];
    case "polyline":
      return guide.path;
    case "polygon":
      return guide.outline;
    case "arrow":
      return [guide.from, guide.to];
  }
}

const uvXs = (guide: GuideShape, mesh: FaceMesh) =>
  anchorsOf(guide).map(({ triangle, bary }) =>
    mesh.triangles[triangle].reduce((sum, i, k) => sum + mesh.uv[i][0] * bary[k], 0),
  );

/** 얼굴 윤곽처럼 양쪽 끝까지 걸친 도형인지 */
function spans(guide: GuideShape, mesh: FaceMesh) {
  const us = uvXs(guide, mesh);
  return us.length > 0 && Math.min(...us) < 0.25 && Math.max(...us) > 0.75;
}

/** 고개 각도에 따른 진하기. UV 가로 0.5가 코, 클수록 본인 기준 왼쪽 */
function turnFade(guide: GuideShape, mesh: FaceMesh, yaw: number) {
  const us = uvXs(guide, mesh);
  if (!us.length) return 1;
  const mean = us.reduce((a, b) => a + b, 0) / us.length;
  if (Math.abs(mean - 0.5) < 0.08)
    return 1 - smoothstep(AWAY_FADE.center[0], AWAY_FADE.center[1], Math.abs(yaw));
  // yaw +면 본인 기준 왼쪽이 멀어진다
  const away = mean > 0.5 ? yaw : -yaw;
  return 1 - smoothstep(AWAY_FADE.side[0], AWAY_FADE.side[1], away);
}

const smoothstep = (lo: number, hi: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

/** 영역 대비 이보다 작은 구멍은 무시한다 */
const MIN_HOLE_AREA = 0.03;

/** 다각형 넓이 (부호 있음) */
function polygonArea(points: Px[]): number {
  let sum = 0;
  points.forEach((p, i) => {
    const q = points[(i + 1) % points.length];
    sum += p.x * q.y - q.x * p.y;
  });
  return sum / 2;
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
function traceSmooth(
  ctx: CanvasRenderingContext2D,
  points: Px[],
  close: boolean,
  /** false면 지금 경로에 이어 붙인다 (구멍을 한 경로로 모을 때) */
  begin = true,
) {
  const n = points.length;
  const pt = (i: number) =>
    close ? points[((i % n) + n) % n] : points[Math.max(0, Math.min(n - 1, i))];
  if (begin) ctx.beginPath();
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
