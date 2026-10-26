import {
  HoldVisibility,
  isGuideVisible,
  isRegionInView,
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

const STYLE = {
  color: "rgba(255, 255, 255, 0.95)",
  // 밝은 피부 위에서도 보이도록 선 아래에 어두운 테두리를 깐다.
  shadow: "rgba(0, 0, 0, 0.45)",
  fill: "rgba(255, 255, 255, 0.12)",
  band: "rgba(255, 255, 255, 0.28)",
  lineWidth: 2.5,
  shadowWidth: 5,
  dash: [10, 7],
  /** 점선이 흐르는 속도 (px/s). 방향을 알려 준다 */
  dashSpeed: 30,
  /** 화살촉 크기 (IOD 기준) */
  arrowHead: 0.12,
  /** 시작점 표시 반지름 (IOD 기준) */
  pointRadius: 0.05,
};

/**
 * 정확하지 않은 가이드는 보여주지 않는다. 공용 규칙(isGuideVisible)대로 추적이 안정적일 때만 보이고,
 * 단계 부위가 모두 가려지면 숨긴다. 깜빡임(hold) 때의 유지는 GuideRenderer가 직전 판정으로 처리한다.
 */
export function isStepVisible(step: GuideStep, frame: FaceFrame | null): boolean {
  if (!frame || !isGuideVisible(frame)) return false;
  if (step.regions.length === 0) return true;
  return step.regions.some((region) => isRegionInView(frame, region));
}

/** 얼굴 위에 튜토리얼 가이드(점선 영역·선·화살표·시작점)를 그린다. */
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
    const dashOffset = -((now / 1000) * STYLE.dashSpeed);

    for (const guide of step.guides) {
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
    switch (guide.type) {
      case "polygon": {
        // 바를 영역: 옅게 채우고 점선으로 테두리
        const points = guide.outline.map(at);
        if (points.length < 3) return;
        tracePath(ctx, points, true);
        ctx.fillStyle = STYLE.fill;
        ctx.fill();
        this.stroke(true, dashOffset);
        return;
      }
      case "polyline": {
        // 그릴 선: 두께만큼 옅은 띠 + 가운데 점선이 진행 방향으로 흐름
        const points = guide.path.map(at);
        if (points.length < 2) return;
        tracePath(ctx, points, false);
        ctx.setLineDash([]);
        ctx.strokeStyle = STYLE.band;
        ctx.lineWidth = Math.max(STYLE.lineWidth, guide.width * unit);
        ctx.stroke();
        this.stroke(true, dashOffset);
        return;
      }
      case "arrow": {
        // 바르는 방향
        const from = at(guide.from);
        const to = at(guide.to);
        tracePath(ctx, [from, to], false);
        this.stroke(true, dashOffset);
        const head = arrowHead(from, to, STYLE.arrowHead * unit);
        if (!head) return;
        tracePath(ctx, head, false);
        this.stroke(false, 0);
        return;
      }
      case "point": {
        // 시작점
        const p = at(guide.at);
        ctx.beginPath();
        ctx.arc(p.x, p.y, Math.max(4, STYLE.pointRadius * unit), 0, Math.PI * 2);
        this.stroke(false, 0);
        return;
      }
    }
  }

  /** 지금 경로를 어두운 테두리 + 흰 선으로 긋는다. */
  private stroke(dashed: boolean, dashOffset: number) {
    const ctx = this.ctx;
    const dash = dashed ? STYLE.dash : [];
    ctx.setLineDash(dash);
    ctx.lineDashOffset = dashOffset;
    ctx.strokeStyle = STYLE.shadow;
    ctx.lineWidth = STYLE.shadowWidth;
    ctx.stroke();
    ctx.strokeStyle = STYLE.color;
    ctx.lineWidth = STYLE.lineWidth;
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

function tracePath(ctx: CanvasRenderingContext2D, points: Px[], close: boolean) {
  ctx.beginPath();
  points.forEach((p, i) => (i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)));
  if (close) ctx.closePath();
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
