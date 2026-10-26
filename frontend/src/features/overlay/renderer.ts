import {
  HoldVisibility,
  isGuideVisible,
  REGIONS,
  toScreen,
  type FaceFrame,
  type Point,
  type RegionName,
  type ViewTransform,
} from "@/features/face";

import { isLayerVisible, isRegionInFrame, type PreparedLayer } from "./layers";
import { UvMaskGl } from "./mask-gl";
import { resolveAnchor, type FaceMesh } from "./mesh";

type Px = { x: number; y: number };

// UV 마스크 렌더러를 만들지 못했을 때 다시 시도하는 간격 (ms)
const MASK_GL_RETRY_MS = 5000;

interface MeshContext {
  frame: FaceFrame;
  mesh: FaceMesh;
  toPx: (p: Point) => Px;
  unit: number;
  mirrored: boolean;
  /** 진하기를 0으로 둘 꼭짓점 */
  fadeOut?: ReadonlySet<number>;
}

let jawVertices: ReadonlySet<number> | null = null;

/**
 * 눈높이 아래쪽(볼 옆·턱) 윤곽 점. 파운데이션이 목과 만나는 곳에서 끊겨 보이지 않게 옅게 한다.
 * 이마 쪽 경계는 피부 분할이 머리카락을 잘라 주어 옅게 하지 않는다.
 */
function jawOf(mesh: FaceMesh) {
  if (!jawVertices) {
    const eyeV = (mesh.uv[33][1] + mesh.uv[263][1]) / 2;
    jawVertices = new Set(REGIONS.faceOval.indices.filter((i) => mesh.uv[i][1] > eyeV));
  }
  return jawVertices;
}

const uvPoint = (mesh: FaceMesh) => (i: number) => ({ x: mesh.uv[i][0], y: mesh.uv[i][1] });
type Box = { x: number; y: number; w: number; h: number };

function context(canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("캔버스 2D를 쓸 수 없습니다");
  return ctx;
}

function boundsOf(points: Px[], margin: number): Box {
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const p of points) {
    x0 = Math.min(x0, p.x);
    y0 = Math.min(y0, p.y);
    x1 = Math.max(x1, p.x);
    y1 = Math.max(y1, p.y);
  }
  return { x: x0 - margin, y: y0 - margin, w: x1 - x0 + margin * 2, h: y1 - y0 + margin * 2 };
}

// 얼굴 윤곽 점의 위쪽 끝은 이마 중간이라, 칠할 때 이마 쪽을 이만큼(IOD 기준) 위로 늘린다.
const FOREHEAD_EXTEND = 0.3;
const FOREHEAD_TOP = 10;
const CHIN = 152;
const EYE_CORNERS = [33, 263] as const;

/**
 * 눈높이 위쪽일수록 얼굴 위 방향으로 밀어 이마 끝까지 덮는 변환.
 * 이마는 위로 갈수록 좁아져, 옆(관자놀이)은 덜 밀어 머리카락을 덮지 않게 한다.
 */
function foreheadWarp(oval: Px[], landmark: (i: number) => Px, unit: number): (p: Px) => Px {
  const top = landmark(FOREHEAD_TOP);
  const chin = landmark(CHIN);
  const len = Math.hypot(top.x - chin.x, top.y - chin.y) || 1;
  const up = { x: (top.x - chin.x) / len, y: (top.y - chin.y) / len };
  const [a, b] = EYE_CORNERS.map(landmark);
  const eye = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  const height = (p: Px) => (p.x - eye.x) * up.x + (p.y - eye.y) * up.y;
  // 얼굴 위 방향에 수직인 가로 거리
  const side = (p: Px) => Math.abs((p.x - eye.x) * -up.y + (p.y - eye.y) * up.x);
  const topHeight = height(top) || 1;
  const halfWidth = Math.max(...oval.map(side)) || 1;
  return (p) => {
    const t = Math.max(0, Math.min(1, height(p) / topHeight));
    const center = Math.max(0, 1 - (side(p) / halfWidth) ** 2);
    const d = FOREHEAD_EXTEND * unit * t * center;
    return { x: p.x + up.x * d, y: p.y + up.y * d };
  };
}

function signedArea([a, b, c]: Px[]) {
  return ((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2;
}

/** 삼각형 꼭짓점 순서 방향 */
function winding(points: Px[]) {
  return Math.sign(signedArea(points));
}

const smoothstep = (lo: number, hi: number, x: number) => {
  const t = Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
  return t * t * (3 - 2 * t);
};

// 고개를 돌리면 먼 쪽 얼굴은 화면에서 눌려 화장이 찌그러진다.
// 정면 대비 눌린 정도가 이 범위면 옅어지다가 사라진다 (넓이 비율).
const SQUASH_FADE = [0.35, 0.7] as const;
// 고개를 돌린 각도(라디안)만큼 먼 쪽 절반 얼굴의 메시 화장을 옅게 한다.
const YAW_FADE = [0.2, 0.45] as const;

/** UV 가로 위치로 본 꼭짓점이 얼굴 어느 쪽인지. 본인 기준 오른쪽 -1 ~ 왼쪽 +1, 가운데(코) 0 */
const sideOf = (u: number) => Math.max(-1, Math.min(1, (u - 0.5) * 5));

const WHITE = (() => {
  if (typeof document === "undefined") return null;
  const c = document.createElement("canvas");
  c.width = c.height = 1;
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, 1, 1);
  return c;
})();
// 부위가 멀어지는 각도(라디안)에서 옅어지다가 사라진다. 가운데(입술)는 옆에서도 보여 더 늦게.
// 추적기는 maxYaw(0.6)를 넘으면 degraded로 보고 화장을 숨기므로, 그 전에 다 옅어지게 맞춘다.
const AWAY_FADE = { side: [0.3, 0.55], center: [0.4, 0.6] } as const;

/** 고개를 돌린 각도에 따른 레이어 진하기 배율. 부위가 여럿이면 가장 잘 보이는 쪽 기준 */
function turnFade(regions: RegionName[], yaw: number) {
  return Math.max(
    ...regions.map((r) => {
      const side = REGIONS[r].side;
      // 얼굴 전체는 메시로 칠해 먼 쪽이 알아서 옅어진다.
      if (r === "faceOval") return 1;
      if (side === "center") {
        return 1 - smoothstep(AWAY_FADE.center[0], AWAY_FADE.center[1], Math.abs(yaw));
      }
      // 본인 기준 왼쪽으로 돌리면(yaw +) 왼쪽 부위가 멀어진다.
      const away = side === "left" ? yaw : -yaw;
      return 1 - smoothstep(AWAY_FADE.side[0], AWAY_FADE.side[1], away);
    }),
  );
}

let uvEyeDistance: number | null = null;

/** UV 위 두 눈 가운데 사이 거리. 화면 IOD와 비교해 정면일 때의 넓이 비율을 구한다. */
function uvIod(mesh: FaceMesh) {
  if (uvEyeDistance === null) {
    const mid = (i: number, j: number) => ({
      x: (mesh.uv[i][0] + mesh.uv[j][0]) / 2,
      y: (mesh.uv[i][1] + mesh.uv[j][1]) / 2,
    });
    const r = mid(33, 133);
    const l = mid(362, 263);
    uvEyeDistance = Math.hypot(l.x - r.x, l.y - r.y);
  }
  return uvEyeDistance;
}

/**
 * 카메라 영상 위에 화장 레이어를 합성한다.
 * 섞기(multiply)가 영상 픽셀과 계산되도록 영상도 같은 캔버스에 그린다.
 */
export class OverlayRenderer {
  private readonly ctx: CanvasRenderingContext2D;
  // 레이어 모양(흰색)을 그리는 곳과, 흐림·색을 입힌 결과를 두는 곳
  private readonly shape = document.createElement("canvas");
  private readonly layer = document.createElement("canvas");
  private readonly shapeCtx = context(this.shape);
  private readonly layerCtx = context(this.layer);
  // 화면 크기로 늘리고 흐린 피부 마스크. 흐림은 화면 전체에 계산되어 레이어마다 하지 않고 프레임마다 한 번만 만든다.
  private readonly skinLayer = document.createElement("canvas");
  private readonly skinCtx = context(this.skinLayer);
  private width = 0;
  private height = 0;
  private dpr = 1;
  private hasSkin = false;
  // 피부 마스크·화면 배치가 같으면 흐린 마스크를 다시 만들지 않는다.
  private skinKey = "";
  // 직전에 보이던 화장만 깜빡임(hold) 동안 유지한다.
  private readonly visibility = new HoldVisibility();
  // undefined: 아직 만들지 않음, null: WebGL을 쓸 수 없음
  private maskGl: UvMaskGl | null | undefined;
  private maskGlFailedAt = 0;
  private disposed = false;
  // 메시 꼭짓점 버퍼. 프레임·레이어마다 새로 만들지 않고, 모자랄 때만 늘린다.
  private meshBuffers = {
    positions: new Float32Array(0),
    uvs: new Float32Array(0),
    alphas: new Float32Array(0),
  };

  private meshBuffersFor(vertices: number) {
    const b = this.meshBuffers;
    if (b.alphas.length < vertices) {
      this.meshBuffers = {
        positions: new Float32Array(vertices * 2),
        uvs: new Float32Array(vertices * 2),
        alphas: new Float32Array(vertices),
      };
    }
    const { positions, uvs, alphas } = this.meshBuffers;
    return {
      positions: positions.subarray(0, vertices * 2),
      uvs: uvs.subarray(0, vertices * 2),
      alphas: alphas.subarray(0, vertices),
    };
  }

  private getMaskGl() {
    // 컨텍스트가 끊겼으면 버리고 다시 만든다. 텍스처도 새 컨텍스트에 다시 올라간다.
    if (this.maskGl?.lost) {
      console.warn("WebGL 컨텍스트가 끊겨 UV 마스크 렌더러를 다시 만듭니다");
      this.maskGl.dispose();
      this.maskGl = undefined;
    }
    // 만들기에 실패했어도 GPU가 돌아왔을 수 있어 잠시 뒤 다시 시도한다.
    if (this.maskGl === null && performance.now() - this.maskGlFailedAt > MASK_GL_RETRY_MS) {
      this.maskGl = undefined;
    }
    if (this.maskGl === undefined) {
      try {
        this.maskGl = new UvMaskGl();
      } catch (e) {
        console.warn("WebGL을 쓸 수 없어 UV 마스크 레이어를 그리지 않습니다", e);
        this.maskGl = null;
        this.maskGlFailedAt = performance.now();
      }
    }
    return this.maskGl;
  }

  constructor(private readonly canvas: HTMLCanvasElement) {
    this.ctx = context(canvas);
  }

  resize(width: number, height: number, dpr: number) {
    this.width = width;
    this.height = height;
    this.dpr = dpr;
    for (const c of [this.canvas, this.shape, this.layer, this.skinLayer]) {
      c.width = Math.round(width * dpr);
      c.height = Math.round(height * dpr);
    }
    this.skinKey = "";
  }

  /** WebGL 컨텍스트와 작업용 캔버스를 놓는다. 이후 render는 아무것도 하지 않는다. */
  dispose() {
    this.disposed = true;
    this.maskGl?.dispose();
    this.maskGl = null;
    for (const c of [this.shape, this.layer, this.skinLayer]) c.width = c.height = 0;
  }

  render(options: {
    /** 카메라 영상. 확인 화면에서는 미리 그린 캔버스를 넣을 수 있다 */
    video: HTMLVideoElement | HTMLCanvasElement | null;
    frame: FaceFrame | null;
    view: ViewTransform | null;
    layers: PreparedLayer[];
    mesh: FaceMesh | null;
    /** false면 영상 없이 레이어만 그린다 (하프미러) */
    drawVideo: boolean;
    /** 얼굴 피부 영역 알파 이미지 (영상과 같은 비율). 없으면 가림을 반영하지 않는다 */
    skinMask?: HTMLCanvasElement | null;
    /** 피부 마스크가 갱신될 때마다 바뀌는 값. 같으면 흐린 마스크를 다시 만들지 않는다 */
    skinVersion?: number;
  }) {
    const { video, frame, view, layers, mesh, drawVideo, skinMask, skinVersion } = options;
    if (this.disposed) return;
    const ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!view) return;

    const size = !video
      ? null
      : video instanceof HTMLVideoElement
        ? { width: video.videoWidth, height: video.videoHeight }
        : { width: video.width, height: video.height };
    if (drawVideo && video && size?.width) this.drawFitted(ctx, video, size, view);
    if (!frame || !mesh) return;
    // 가이드와 같은 공용 규칙으로, 추적이 불안정하면(degraded) 화장도 숨긴다.
    if (!this.visibility.update(frame, () => isGuideVisible(frame))) return;
    const visible = layers.filter((prepared) => isLayerVisible(prepared.layer, frame));

    this.hasSkin = Boolean(skinMask && size?.width && visible.length > 0);
    const skinKey = this.hasSkin
      ? [
          skinVersion,
          size!.width,
          size!.height,
          view.scale,
          view.offsetX,
          view.offsetY,
          view.mirrored,
        ].join()
      : "";
    if (this.hasSkin && (skinKey !== this.skinKey || skinVersion === undefined)) {
      const sk = this.skinCtx;
      sk.clearRect(0, 0, this.skinLayer.width, this.skinLayer.height);
      // 작은 마스크를 크게 늘려 생기는 계단을 흐려서 숨긴다 (마스크 한 칸 크기만큼).
      const cell = (size!.width * view.scale) / skinMask!.width;
      this.drawFitted(sk, skinMask!, size!, view, cell);
    }
    this.skinKey = skinKey;

    const toPx = (p: Point) => toScreen(p, frame.imageSize, view);
    // IOD = 1 단위를 화면 픽셀로
    const unit = frame.iod * view.scale;

    for (const prepared of visible) {
      this.drawLayer(prepared, frame, mesh, toPx, unit, view.mirrored);
    }
  }

  /** 영상 크기(size) 기준 이미지를 영상과 같은 위치·반전으로 화면에 그린다. */
  private drawFitted(
    ctx: CanvasRenderingContext2D,
    image: CanvasImageSource,
    size: { width: number; height: number },
    view: ViewTransform,
    blurPx = 0,
  ) {
    ctx.filter = blurPx > 0 ? `blur(${blurPx * this.dpr}px)` : "none";
    const w = size.width * view.scale;
    const h = size.height * view.scale;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    if (view.mirrored) {
      ctx.translate(view.offsetX + w, view.offsetY);
      ctx.scale(-1, 1);
      ctx.drawImage(image, 0, 0, w, h);
    } else {
      ctx.drawImage(image, view.offsetX, view.offsetY, w, h);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.filter = "none";
  }

  private drawLayer(
    { layer, mask }: PreparedLayer,
    frame: FaceFrame,
    mesh: FaceMesh,
    toPx: (p: Point) => Px,
    unit: number,
    mirrored: boolean,
  ) {
    // uvMask는 마스크 자체에 흐림이 들어 있어 feather를 쓰지 않는다.
    const featherPx = layer.shape === "uvMask" ? 0 : (layer.feather ?? 0) * unit;
    const sctx = this.shapeCtx;
    const dpr = this.dpr;

    // 1. 모양을 흰색으로 그린다 (CSS 픽셀 좌표)
    let points: Px[];
    let draw: (box: Box) => void;
    let margin = featherPx + 2;

    if (layer.shape === "polygon") {
      const outline = (name: RegionName) =>
        REGIONS[name].indices.map((i) => toPx(frame.landmarks[i]));
      const fillPolygons = (list: Px[][], op: GlobalCompositeOperation) => {
        sctx.fillStyle = "#fff";
        sctx.globalCompositeOperation = op;
        for (const poly of list) {
          sctx.beginPath();
          poly.forEach((p, i) => (i === 0 ? sctx.moveTo(p.x, p.y) : sctx.lineTo(p.x, p.y)));
          sctx.closePath();
          sctx.fill();
        }
        sctx.globalCompositeOperation = "source-over";
      };
      const holes = (layer.exclude ?? []).map(outline);

      // 얼굴 전체는 외곽선 하나로 칠하면 고개를 돌렸을 때 먼 쪽이 얼굴 밖까지 걸친다.
      // 메시 삼각형으로 칠해 눌린 쪽은 옅게 하고, 이마는 위로 늘린다. WebGL이 없으면 외곽선으로 칠한다.
      const gl = layer.regions.includes("faceOval") ? this.getMaskGl() : null;
      if (gl && WHITE) {
        const warp = foreheadWarp(outline("faceOval"), (i) => toPx(frame.landmarks[i]), unit);
        const all = mesh.triangles.map((_, i) => i);
        // 턱선 쪽 윤곽 점은 진하기 0으로 두어 자연스럽게 사라지게 한다.
        const shape = this.meshShape(gl, WHITE, all, (k) => mesh.triangles[k].map(uvPoint(mesh)), {
          frame,
          mesh,
          toPx: (p) => warp(toPx(p)),
          unit,
          mirrored,
          fadeOut: jawOf(mesh),
        });
        points = shape.points;
        draw = (box) => {
          shape.draw(box);
          fillPolygons(holes, "destination-out");
        };
      } else {
        // 고개를 많이 돌려 사라진 쪽 부위는 칠하지 않는다.
        const fills = layer.regions
          .filter((r) => turnFade([r], frame.pose.yaw) > 0 && isRegionInFrame(frame, r))
          .map(outline);
        points = fills.flat();
        draw = () => {
          fillPolygons(fills, "source-over");
          fillPolygons(holes, "destination-out");
        };
      }
    } else if (layer.shape === "polyline") {
      if (!layer.path?.length || !layer.width) return;
      points = layer.path.map((a) => toPx(resolveAnchor(a, mesh, frame.landmarks)));
      const lineWidth = layer.width * unit;
      margin += lineWidth / 2;
      draw = () => {
        sctx.strokeStyle = "#fff";
        sctx.lineWidth = lineWidth;
        sctx.lineCap = layer.lineCap ?? "round";
        sctx.lineJoin = "round";
        sctx.beginPath();
        points.forEach((p, i) => (i === 0 ? sctx.moveTo(p.x, p.y) : sctx.lineTo(p.x, p.y)));
        sctx.stroke();
      };
    } else {
      const gl = this.getMaskGl();
      if (!mask || !gl) return;
      const shape = this.meshShape(gl, mask.image, mask.triangles, (k) => mask.uv[k], {
        frame,
        mesh,
        toPx,
        unit,
        mirrored,
      });
      points = shape.points;
      margin = 2;
      draw = shape.draw;
    }

    if (points.length === 0) return;
    const box = this.toDeviceBox(boundsOf(points, margin));
    if (!box) return;

    sctx.setTransform(1, 0, 0, 1, 0, 0);
    sctx.clearRect(box.x, box.y, box.w, box.h);
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw(box);
    sctx.setTransform(1, 0, 0, 1, 0, 0);

    // 2. 흐림: 경계에서 안팎으로 feather/2씩 퍼지도록 가우시안 σ ≈ feather/4
    const lctx = this.layerCtx;
    lctx.clearRect(box.x, box.y, box.w, box.h);
    lctx.filter = featherPx > 0.5 ? `blur(${(featherPx / 4) * dpr}px)` : "none";
    lctx.drawImage(this.shape, box.x, box.y, box.w, box.h, box.x, box.y, box.w, box.h);
    lctx.filter = "none";

    // 3. 색을 입힌다 (모양의 알파 = 진하기)
    lctx.globalCompositeOperation = "source-in";
    lctx.fillStyle = layer.color!;
    lctx.fillRect(box.x, box.y, box.w, box.h);

    // 앞머리·손처럼 얼굴 피부가 아닌 곳은 지운다.
    if (this.hasSkin) {
      lctx.globalCompositeOperation = "destination-in";
      lctx.drawImage(this.skinLayer, box.x, box.y, box.w, box.h, box.x, box.y, box.w, box.h);
    }
    lctx.globalCompositeOperation = "source-over";

    // 4. 합성: normal = 피부×(1−a) + 색×a, multiply = 피부×(1−a) + 피부×색×a
    const ctx = this.ctx;
    // uvMask는 메시 꼭짓점마다 고개 돌림을 반영하므로 레이어 단위로 또 곱하지 않는다.
    const turn = layer.shape === "uvMask" ? 1 : turnFade(layer.regions, frame.pose.yaw);
    const opacity = layer.opacity * turn;
    if (opacity <= 0) return;
    ctx.globalAlpha = Math.max(0, Math.min(1, opacity));
    ctx.globalCompositeOperation = layer.blend === "multiply" ? "multiply" : "source-over";
    ctx.drawImage(this.layer, box.x, box.y, box.w, box.h, box.x, box.y, box.w, box.h);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }

  /**
   * 메시 삼각형에 이미지를 입혀 그리는 모양.
   * 뒤집힌 삼각형은 빼고, 화면에서 눌렸거나 고개를 돌려 멀어진 쪽은 옅게 한다.
   */
  private meshShape(
    gl: UvMaskGl,
    image: TexImageSource,
    triangles: number[],
    uvOf: (k: number) => Px[],
    { frame, mesh, toPx, unit, mirrored, fadeOut }: MeshContext,
  ) {
    const dpr = this.dpr;
    // 거울 반전이면 앞면의 방향도 뒤집힌다.
    const front = mirrored ? -1 : 1;
    // 정면 얼굴이면 화면 넓이 ≈ UV 넓이 × (화면 IOD / UV IOD)²
    const expected = (unit / uvIod(mesh)) ** 2;
    const visible: { ids: number[]; dst: Px[]; src: Px[]; weight: number }[] = [];
    triangles.forEach((t, k) => {
      const ids = mesh.triangles[t];
      const dst = ids.map((i) => toPx(frame.landmarks[i]));
      const src = uvOf(k);
      if (winding(dst) !== front * winding(src)) return;
      const squash = Math.abs(signedArea(dst)) / (Math.abs(signedArea(src)) * expected || 1);
      visible.push({ ids, dst, src, weight: smoothstep(SQUASH_FADE[0], SQUASH_FADE[1], squash) });
    });

    // 이웃 삼각형끼리 진하기가 끊기지 않도록 꼭짓점마다 평균을 낸다.
    const sum = new Map<number, { w: number; n: number }>();
    for (const { ids, weight } of visible) {
      for (const i of ids) {
        const v = sum.get(i) ?? { w: 0, n: 0 };
        v.w += weight;
        v.n += 1;
        sum.set(i, v);
      }
    }
    // 본인 기준 왼쪽으로 돌리면(yaw +) 왼쪽이 멀어진다.
    const yaw = frame.pose.yaw;
    const yawWeight = (i: number) =>
      1 - smoothstep(YAW_FADE[0], YAW_FADE[1], yaw * sideOf(mesh.uv[i][0]));

    // 버퍼는 다음 meshShape에서 덮어쓰므로, draw는 이 레이어를 그리는 동안 바로 불러야 한다.
    const { positions, uvs, alphas } = this.meshBuffersFor(visible.length * 3);
    const points: Px[] = [];
    let n = 0;
    for (const { ids, dst, src } of visible) {
      for (let j = 0; j < 3; j++, n++) {
        const v = sum.get(ids[j])!;
        positions[n * 2] = dst[j].x * dpr;
        positions[n * 2 + 1] = dst[j].y * dpr;
        uvs[n * 2] = src[j].x;
        uvs[n * 2 + 1] = src[j].y;
        alphas[n] = fadeOut?.has(ids[j]) ? 0 : (v.w / v.n) * yawWeight(ids[j]);
      }
      points.push(...dst);
    }

    const draw = (box: Box) => {
      gl.draw(image, positions, uvs, alphas, this.shape.width, this.shape.height);
      const sctx = this.shapeCtx;
      sctx.save();
      sctx.setTransform(1, 0, 0, 1, 0, 0);
      // 레이어가 차지하는 범위만 옮긴다.
      sctx.drawImage(gl.canvas, box.x, box.y, box.w, box.h, box.x, box.y, box.w, box.h);
      sctx.restore();
    };
    return { points, draw };
  }

  /** CSS 픽셀 범위를 캔버스 안쪽의 정수 기기 픽셀 범위로 바꾼다. */
  private toDeviceBox(box: Box): Box | null {
    const d = this.dpr;
    const x0 = Math.max(0, Math.floor(box.x * d));
    const y0 = Math.max(0, Math.floor(box.y * d));
    const x1 = Math.min(Math.round(this.width * d), Math.ceil((box.x + box.w) * d));
    const y1 = Math.min(Math.round(this.height * d), Math.ceil((box.y + box.h) * d));
    if (x1 <= x0 || y1 <= y0) return null;
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }
}
