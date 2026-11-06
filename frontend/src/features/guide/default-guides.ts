// 외부 분석 결과가 없을 때 쓰는 9개 부위 기본 가이드. 랜드마크 번호로 정의하고 MeshAnchor로 바꿔
// 외부 가이드 파일과 같은 형식(GuideSet)으로 돌려준다.
// 픽스처 생성 스크립트도 Node에서 바로 읽으므로 다른 모듈을 값으로 import하지 않는다.
import type { GuideShape, MeshAnchor, RegionName } from "@/features/face";
import type { FaceMesh } from "@/features/overlay";

import type { GuideSet, GuideStep } from "./types";

type Uv = { x: number; y: number };
type RegionIndices = Record<RegionName, { indices: readonly number[] }>;

const round = (v: number) => Number(v.toFixed(4));

function barycentric(p: Uv, [a, b, c]: Uv[]): [number, number, number] {
  const v0 = { x: b.x - a.x, y: b.y - a.y };
  const v1 = { x: c.x - a.x, y: c.y - a.y };
  const v2 = { x: p.x - a.x, y: p.y - a.y };
  const det = v0.x * v1.y - v1.x * v0.y;
  const wb = (v2.x * v1.y - v1.x * v2.y) / det;
  const wc = (v0.x * v2.y - v2.x * v0.y) / det;
  return [1 - wb - wc, wb, wc];
}

/** 메시 UV 위의 점을 MeshAnchor로 바꾸는 도구 */
export function anchorTools(mesh: FaceMesh) {
  const uvPt = (i: number): Uv => ({ x: mesh.uv[i][0], y: mesh.uv[i][1] });
  // 점마다 삼각형 전체를 훑으므로 꼭짓점 UV는 한 번만 꺼내 둔다.
  const triangleUvs = mesh.triangles.map((tri) => tri.map(uvPt));
  // 랜드마크가 꼭짓점인 첫 삼각형과 그 안의 자리. 꼭짓점 그대로인 기준점은 훑지 않고 바로 쓴다.
  const vertexSlots = new Map<number, { triangle: number; slot: number }>();
  mesh.triangles.forEach((tri, triangle) =>
    tri.forEach((vertex, slot) => {
      if (!vertexSlots.has(vertex)) vertexSlots.set(vertex, { triangle, slot });
    }),
  );

  /** 점을 품은 삼각형 기준으로 바꾼다. 삼각형 밖이면 가장 가까운 삼각형 (음수 비율) */
  const anchorAt = (p: Uv): MeshAnchor => {
    let best: { index: number; bary: [number, number, number]; outside: number } | null = null;
    triangleUvs.forEach((uvs, index) => {
      const bary = barycentric(p, uvs);
      const outside = -Math.min(...bary);
      if (!best || outside < best.outside) best = { index, bary, outside };
    });
    const { index, bary } = best!;
    const b1 = round(bary[1]);
    const b2 = round(bary[2]);
    return { triangle: index, bary: [round(1 - b1 - b2), b1, b2] };
  };

  /** 랜드마크 i */
  const at = (i: number): MeshAnchor => {
    const hit = vertexSlots.get(i);
    if (!hit) return anchorAt(uvPt(i));
    const bary: [number, number, number] = [0, 0, 0];
    bary[hit.slot] = 1;
    return { triangle: hit.triangle, bary };
  };
  /** 랜드마크 i에서 j 쪽으로 t만큼 간 자리 */
  const between = (i: number, j: number, t = 0.5) =>
    anchorAt({
      x: uvPt(i).x + (uvPt(j).x - uvPt(i).x) * t,
      y: uvPt(i).y + (uvPt(j).y - uvPt(i).y) * t,
    });
  const outline = (indices: readonly number[]): GuideShape => ({
    type: "polygon",
    outline: indices.map(at),
  });

  return { uvPt, anchorAt, at, between, outline };
}

// 아이라인: 눈 안쪽 1/3 지점에서 눈꼬리까지 윗눈꺼풀 점(속눈썹 뿌리)을 그대로 따라가고, 꼬리는 아래 속눈썹
// 라인의 연장선으로 짧게 뺀다 (눈매 방향 그대로, 위로 올리지 않음). 아래 눈꺼풀 쪽으로 내리면 실기기에서
// 선이 흰자 위로 내려간다.
const WING_LENGTH = 0.15; // 눈 너비 대비

// 윗눈꺼풀 점 (안쪽 1/3 → 눈꼬리 직전). 눈꼬리 점은 아래로 꺾여 있어 건너뛴다
const EYELINER = {
  right: {
    upper: [157, 158, 159, 160, 161, 246],
    lowerNearOuter: 163,
    inner: 133,
    outer: 33,
  },
  left: {
    upper: [384, 385, 386, 387, 388, 466],
    lowerNearOuter: 390,
    inner: 362,
    outer: 263,
  },
};

// 애교살 띠 두께: 아래 속눈썹 선에서 눈 밑 고리까지 거리 대비.
// 영상에서 찾은 영역은 바른 곳 전체지만, 기본 가이드는 얇게 얹으라는 안내라 절반만 쓴다
const UNDER_EYE_DEPTH = 0.5;

const unit = (v: Uv): Uv => {
  const len = Math.hypot(v.x, v.y) || 1;
  return { x: v.x / len, y: v.y / len };
};

/** 아이라인 경로. 미리보기 레이어도 같은 경로를 쓴다 */
export function eyelinerPaths(mesh: FaceMesh): { right: MeshAnchor[]; left: MeshAnchor[] } {
  const { uvPt, anchorAt, at } = anchorTools(mesh);
  const path = ({ upper, lowerNearOuter, inner, outer }: typeof EYELINER.right) => {
    const points = upper.map(at);
    const corner = uvPt(outer);
    const dir = unit({
      x: corner.x - uvPt(lowerNearOuter).x,
      y: corner.y - uvPt(lowerNearOuter).y,
    });
    const length = Math.hypot(corner.x - uvPt(inner).x, corner.y - uvPt(inner).y) * WING_LENGTH;
    points.push(anchorAt({ x: corner.x + dir.x * length, y: corner.y + dir.y * length }));
    return points;
  };
  return { right: path(EYELINER.right), left: path(EYELINER.left) };
}

/**
 * 9개 부위 기본 가이드를 바르는 순서대로 만든다. 좌우는 사용자 신체 기준이고, 오른쪽을 먼저 쓴다.
 * regions에는 부위 정의(REGIONS)를 넘긴다.
 */
export function buildDefaultGuideSet(mesh: FaceMesh, regions: RegionIndices): GuideSet {
  const { uvPt, anchorAt, at, between, outline } = anchorTools(mesh);
  const arrow = (from: MeshAnchor, to: MeshAnchor): GuideShape => ({ type: "arrow", from, to });
  const point = (anchor: MeshAnchor): GuideShape => ({ type: "point", at: anchor });
  const eyeliner = eyelinerPaths(mesh);
  /** 얼굴 외곽 점들과, 그 점들을 코끝 쪽으로 조금 들인 선 사이의 띠 */
  const contourBand = (edge: number[]): GuideShape => ({
    type: "polygon",
    outline: [...edge.map(at), ...[...edge].reverse().map((i) => between(i, 4, 0.12))],
  });
  /** 윗눈꺼풀 선(바깥 → 안쪽)과, [눈꺼풀 점, 눈썹 점]을 40% 올라간 선(안쪽 → 바깥) 사이의 띠 */
  const lidBand = (lid: number[], toBrow: [number, number][]): GuideShape => ({
    type: "polygon",
    outline: [...lid.map(at), ...toBrow.map(([i, j]) => between(i, j, 0.4))],
  });
  /** 아래 속눈썹 선(바깥 → 안쪽)과, 그 점들을 눈 밑 고리 쪽으로 UNDER_EYE_DEPTH만큼 내린 선(안쪽 → 바깥) 사이의 띠 */
  const underBand = (lash: number[], ring: number[]): GuideShape => ({
    type: "polygon",
    outline: [
      ...lash.map(at),
      ...lash.map((i, k) => between(i, ring[k], UNDER_EYE_DEPTH)).reverse(),
    ],
  });
  // 눈두덩이 띠와 화살표 (윗눈꺼풀 ~ 눈썹까지의 아래쪽 40%, 쌍꺼풀 라인 높이)
  const upperLid = [
    lidBand(
      [33, 246, 161, 160, 159, 158, 157, 173, 133],
      [
        [133, 55],
        [158, 65],
        [159, 52],
        [161, 53],
        [33, 46],
      ],
    ),
    lidBand(
      [263, 466, 388, 387, 386, 385, 384, 398, 362],
      [
        [362, 285],
        [385, 295],
        [386, 282],
        [388, 283],
        [263, 276],
      ],
    ),
    arrow(between(157, 65, 0.2), between(161, 53, 0.2)),
    arrow(between(384, 295, 0.2), between(388, 283, 0.2)),
  ];
  // 애교살 띠: 아래 속눈썹 선 → 눈 밑 고리
  const underEye = [
    underBand(
      [33, 7, 163, 144, 145, 153, 154, 155, 133],
      [226, 31, 228, 229, 230, 231, 232, 233, 244],
    ),
    underBand(
      [263, 249, 390, 373, 374, 380, 381, 382, 362],
      [446, 261, 448, 449, 450, 451, 452, 453, 464],
    ),
  ];

  const browHairs = (pairs: [number, number][]) => buildBrowHairs(mesh, pairs);
  /**
   * 속눈썹: [눈꺼풀 점, 눈썹 점] 쌍을 안쪽 → 바깥쪽 순서로 받아, 눈꺼풀을 따라 가늘고 짧은 속눈썹을 촘촘히 만든다.
   * 눈썹 쪽으로 뻗되 바깥쪽으로 갈수록 눈꼬리 쪽으로 눕는다.
   */
  const lashes = (pairs: [number, number][], count = 12): GuideShape[] => {
    const lerp = (p: Uv, q: Uv, t: number): Uv => ({
      x: p.x + (q.x - p.x) * t,
      y: p.y + (q.y - p.y) * t,
    });
    const along = (s: number, side: 0 | 1): Uv => {
      const x = Math.min(0.999, Math.max(0, s)) * (pairs.length - 1);
      const i = Math.floor(x);
      return lerp(uvPt(pairs[i][side]), uvPt(pairs[i + 1][side]), x - i);
    };
    const outward = unit({
      x: uvPt(pairs[pairs.length - 1][0]).x - uvPt(pairs[0][0]).x,
      y: uvPt(pairs[pairs.length - 1][0]).y - uvPt(pairs[0][0]).y,
    });
    // 길이를 조금씩 흐트러뜨린다 (같은 값이 나오는 고정 난수)
    const jitter = (k: number) => {
      const x = Math.sin(k * 78.233) * 43758.5453;
      return x - Math.floor(x);
    };
    return Array.from({ length: count }, (_, k): GuideShape => {
      const s = k / (count - 1);
      const root = along(s, 0);
      const toBrow = { x: along(s, 1).x - root.x, y: along(s, 1).y - root.y };
      // 끝이 눈꺼풀 가장자리 바로 위 점들(눈썹까지의 11~16%)보다 아래에 있어야 눈을 감을 때 같이 내려온다
      const reach = Math.hypot(toBrow.x, toBrow.y) * (0.05 + 0.03 * s + 0.01 * jitter(k));
      const up = unit(toBrow);
      const lean = 0.15 + 0.6 * s;
      const tip = {
        x: root.x + (up.x + outward.x * lean) * reach,
        y: root.y + (up.y + outward.y * lean) * reach,
      };
      const mid = {
        x: root.x + (up.x + outward.x * lean * 0.4) * reach * 0.5,
        y: root.y + (up.y + outward.y * lean * 0.4) * reach * 0.5,
      };
      return {
        type: "polyline",
        path: [anchorAt(root), anchorAt(mid), anchorAt(tip)],
        width: 0.006,
        brush: true,
      };
    });
  };

  const steps: Omit<GuideStep, "order" | "source">[] = [
    {
      // 얼굴 윤곽 전체, 얼굴 가운데에서 볼·이마·턱 바깥쪽으로
      stepId: "foundation",
      title: "베이스: 얼굴 가운데에서 바깥쪽으로 얇게 펴 발라요",
      regions: ["faceOval"],
      guides: [
        outline(regions.faceOval.indices),
        arrow(at(205), between(205, 93, 0.7)),
        arrow(at(425), between(425, 323, 0.7)),
        arrow(at(9), between(9, 10, 0.7)),
        arrow(at(18), between(18, 152, 0.7)),
      ],
    },
    {
      // 얼굴 외곽만 얇게: 옆광대 아래(234·454) ~ 턱선(172·397), 안쪽 경계는 코끝(4) 쪽으로 조금 들인 선
      stepId: "contour",
      title: "쉐딩: 옆광대 아래부터 턱선까지 바깥쪽에서 안쪽으로 짧게 쓸어요",
      regions: ["rightCheek", "leftCheek"],
      guides: [
        contourBand([234, 93, 132, 58, 172]),
        point(at(132)),
        arrow(at(132), between(132, 4, 0.15)),
        contourBand([454, 323, 361, 288, 397]),
        point(at(361)),
        arrow(at(361), between(361, 4, 0.15)),
      ],
    },
    {
      // 작게 세 군데: 미간 아래 콧대, 눈 밑 앞쪽, 턱 끝.
      // 얼굴을 가까이 대면 윤곽이 화면 밖으로 나가므로, 그리는 곳 옆 부위(눈·입술)로 숨김을 판정한다.
      stepId: "highlight",
      title: "하이라이트: 콧대 위쪽·눈 밑 앞쪽·턱 끝에 살짝 얹어요",
      regions: ["rightEye", "leftEye", "lipsOuter"],
      guides: [
        outline([193, 417, 351, 419, 196, 122]),
        outline([230, 231, 232, 121, 47, 100, 119]),
        outline([450, 451, 452, 350, 277, 329, 348]),
        outline([201, 421, 428, 208]),
      ],
    },
    {
      // 볼 전체 외접 범위를 유지한 둥근 타원. 시작점·방향은 기존과 같다
      stepId: "blush",
      title: "블러셔: 볼 앞에서 광대 쪽으로 둥글게 펴요",
      regions: ["rightCheek", "leftCheek"],
      guides: buildBlushGuides(mesh, regions),
    },
    {
      // 앞머리(55·107)에서 꼬리(46·70)까지 결 방향 붓 자국. 결이 채울 영역을 보여 주므로 윤곽은 따로 그리지 않는다
      stepId: "brow",
      title: "눈썹: 결을 따라 빈 곳만 가볍게 채워요",
      regions: ["rightBrow", "leftBrow"],
      guides: [
        ...browHairs([
          [55, 107],
          [65, 66],
          [52, 105],
          [53, 63],
          [46, 70],
        ]),
        ...browHairs([
          [285, 336],
          [295, 296],
          [282, 334],
          [283, 293],
          [276, 300],
        ]),
      ],
    },
    {
      // 바른 자리를 모를 때의 기본값. 아이섀도는 눈두덩이와 애교살 어느 쪽에도 바르므로 둘 다 안내한다
      stepId: "eyeshadow",
      title: "아이섀도: 눈두덩이는 쌍꺼풀 라인까지 펴 바르고 애교살은 얇게 얹어요",
      regions: ["rightEye", "leftEye"],
      guides: [...upperLid, ...underEye],
    },
    {
      stepId: "eyeshadowUpper",
      title: "아이섀도: 쌍꺼풀 라인 높이까지 안쪽에서 바깥쪽으로 펴 발라요",
      regions: ["rightEye", "leftEye"],
      guides: upperLid,
    },
    {
      stepId: "eyeshadowUnder",
      title: "애교살: 아래 속눈썹 선을 따라 얇게 얹어요",
      regions: ["rightEye", "leftEye"],
      guides: underEye,
    },
    {
      stepId: "eyeliner",
      title: "아이라인: 속눈썹 사이를 채우고 꼬리는 눈매 따라 짧게 빼요",
      regions: ["rightEye", "leftEye"],
      guides: [
        point(eyeliner.right[0]),
        { type: "polyline", path: eyeliner.right, width: 0.03 },
        point(eyeliner.left[0]),
        { type: "polyline", path: eyeliner.left, width: 0.03 },
      ],
    },
    {
      // 윗눈꺼풀(속눈썹 뿌리) 가운데~바깥쪽에서 눈썹 쪽으로 쓸어 올리는 속눈썹 결
      stepId: "mascara",
      title: "마스카라: 속눈썹 뿌리에서 위로 쓸어 올려요",
      regions: ["rightEye", "leftEye"],
      guides: [
        ...lashes([
          [157, 55],
          [158, 65],
          [159, 52],
          [160, 53],
          [161, 53],
          [246, 46],
        ]),
        ...lashes([
          [384, 285],
          [385, 295],
          [386, 282],
          [387, 283],
          [388, 283],
          [466, 276],
        ]),
      ],
    },
    {
      stepId: "lip",
      title: "립: 입술 안쪽에 바르고 바깥쪽으로 톡톡 펴 그라데이션해요",
      regions: ["lipsOuter"],
      guides: [
        // AI 립 영역처럼 입 안은 뺀다
        { ...outline(regions.lipsOuter.indices), exclude: ["lipsInner"] },
        point(between(0, 17)),
        arrow(between(0, 17), between(61, 0, 0.15)),
        arrow(between(0, 17), between(291, 0, 0.15)),
      ],
    },
  ];

  return {
    meshVersion: "v1",
    steps: steps.map((step, i) => ({ ...step, order: i + 1, source: "template" })),
  };
}

/** 결정된 기본 눈썹: 중앙은 숱을 늘리고 앞머리·꼬리는 줄인 결 40개. */
export function buildBrowHairs(mesh: FaceMesh, pairs: [number, number][]): GuideShape[] {
  const { uvPt, anchorAt } = anchorTools(mesh);
  const lerp = (a: { x: number; y: number }, b: { x: number; y: number }, t: number) => ({
    x: a.x + (b.x - a.x) * t,
    y: a.y + (b.y - a.y) * t,
  });
  const at = (s: number, h: number) => {
    const x = Math.min(0.999, s) * (pairs.length - 1),
      i = Math.floor(x);
    const lower = lerp(uvPt(pairs[i][0]), uvPt(pairs[i + 1][0]), x - i);
    const upper = lerp(uvPt(pairs[i][1]), uvPt(pairs[i + 1][1]), x - i);
    // 기존 눈썹의 높이를 대부분 유지하고 끝부분만 완만하게 좁힌다.
    const tail = Math.max(0, (s - 0.65) / 0.35);
    const half = 0.46 * (1 - 0.45 * tail);
    return anchorAt(lerp(lower, upper, 0.5 + (h * 2 - 1) * half));
  };
  const jitter = (k: number) => {
    const v = Math.sin(k * 12.9898) * 43758.5453;
    return v - Math.floor(v);
  };
  // 밀도의 누적분포를 반대로 읽어 중앙은 숱을 늘리고 앞머리·꼬리는 줄인다.
  // 고정 난수와 함께 쓰므로 프레임마다 결 위치가 바뀌지 않는다.
  const cdf = [0];
  for (let k = 1; k <= 128; k++) {
    const t = (k - 0.5) / 128;
    cdf.push(cdf[k - 1] + 0.22 + 0.78 * Math.sin(Math.PI * t) ** 1.2);
  }
  const position = (u: number) => {
    const target = u * cdf[128];
    const i = cdf.findIndex((v) => v >= target);
    return 0.025 + (0.92 * (i - 1 + (target - cdf[i - 1]) / (cdf[i] - cdf[i - 1]))) / 128;
  };
  return Array.from({ length: 40 }, (_, k): GuideShape => {
    const row = k % 2,
      col = Math.floor(k / 2);
    const s = position((col + 0.3 + row * 0.4 + jitter(k) * 0.15) / 20);
    const root = 0.08 + row * 0.22 + jitter(k + 70) * 0.07;
    const tail = Math.max(0, (s - 0.65) / 0.35);
    const tip = Math.min(0.95, root + (0.66 - 0.22 * tail) * (0.8 + jitter(k + 100) * 0.2));
    // 기존 결 방향을 유지하되 끝점이 꼬리 끝에 몰리지 않게 한다.
    const lean = Math.min(0.015 + 0.09 * s, (0.99 - s) * 0.7);
    return {
      type: "polyline",
      brush: true,
      width: 0.013 * (1 - 0.25 * tail),
      path: [at(s, root), at(s + lean * 0.45, (root + tip) / 2 + 0.035), at(s + lean, tip)],
    };
  });
}

/** 볼 전체 외접 범위의 타원과 기존 시작점·방향. */
export function buildBlushGuides(mesh: FaceMesh, regions: RegionIndices): GuideShape[] {
  const { uvPt, anchorAt, between } = anchorTools(mesh);
  const ellipse = (indices: readonly number[]): GuideShape => {
    const points = indices.map(uvPt);
    const xs = points.map((p) => p.x),
      ys = points.map((p) => p.y);
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2,
      cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const rx = (Math.max(...xs) - Math.min(...xs)) / 2,
      ry = (Math.max(...ys) - Math.min(...ys)) / 2;
    return {
      type: "polygon",
      outline: Array.from({ length: 32 }, (_, k) => {
        const t = (k * Math.PI) / 16;
        return anchorAt({ x: cx + rx * Math.cos(t), y: cy + ry * Math.sin(t) });
      }),
    };
  };
  return [
    ellipse(regions.rightCheek.indices),
    ellipse(regions.leftCheek.indices),
    { type: "point", at: between(101, 50) },
    { type: "arrow", from: between(101, 50), to: between(123, 117, 0.3) },
    { type: "point", at: between(330, 280) },
    { type: "arrow", from: between(330, 280), to: between(352, 346, 0.3) },
  ];
}
