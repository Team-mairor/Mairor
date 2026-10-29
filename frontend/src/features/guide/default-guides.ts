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
function anchorTools(mesh: FaceMesh) {
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

// 아이라인: 눈 안쪽 1/3 지점에서 눈꼬리까지 속눈썹 라인을 따라가고, 꼬리는 아래 속눈썹 라인의 연장선으로
// 짧게 뺀다 (눈매 방향 그대로, 위로 올리지 않음). MediaPipe 윗눈꺼풀 점은 눈꺼풀 가장자리라, 선이 눈꺼풀
// 위로 뜨지 않게 아래 눈꺼풀 쪽으로 조금 내린다.
const LASH_LINE_SHIFT = 0.12; // 눈 뜬 높이 대비
const WING_LENGTH = 0.15; // 눈 너비 대비

// 윗눈꺼풀과 같은 자리의 아래 눈꺼풀 점 (안쪽 1/3 → 눈꼬리 직전). 눈꼬리 점은 아래로 꺾여 있어 건너뛴다
const EYELINER = {
  right: {
    upper: [157, 158, 159, 160, 161, 246],
    lower: [154, 153, 145, 144, 163, 7],
    lowerNearOuter: 163,
    inner: 133,
    outer: 33,
  },
  left: {
    upper: [384, 385, 386, 387, 388, 466],
    lower: [381, 380, 374, 373, 390, 249],
    lowerNearOuter: 390,
    inner: 362,
    outer: 263,
  },
};

const unit = (v: Uv): Uv => {
  const len = Math.hypot(v.x, v.y) || 1;
  return { x: v.x / len, y: v.y / len };
};

/** 아이라인 경로. 미리보기 레이어도 같은 경로를 쓴다 */
export function eyelinerPaths(mesh: FaceMesh): { right: MeshAnchor[]; left: MeshAnchor[] } {
  const { uvPt, anchorAt } = anchorTools(mesh);
  const path = ({ upper, lower, lowerNearOuter, inner, outer }: typeof EYELINER.right) => {
    const points = upper.map((i, k) => {
      const u = uvPt(i);
      const l = uvPt(lower[k]);
      return anchorAt({
        x: u.x + (l.x - u.x) * LASH_LINE_SHIFT,
        y: u.y + (l.y - u.y) * LASH_LINE_SHIFT,
      });
    });
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
  const { at, between, outline } = anchorTools(mesh);
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

  const steps: Omit<GuideStep, "order" | "source">[] = [
    {
      // 얼굴 윤곽 전체, 얼굴 가운데에서 볼·이마·턱 바깥쪽으로
      stepId: "base",
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
      // 볼 앞쪽(웃으면 올라오는 곳, 눈동자 아래). 코 옆에서 바깥으로 거의 가로로
      stepId: "blush",
      title: "블러셔: 볼 앞쪽에 코 옆에서 바깥쪽으로 둥글게 펴요",
      regions: ["rightCheek", "leftCheek"],
      guides: [
        // 바깥쪽은 점이 세로로 늘어서 있어, 광대 쪽(123·352)으로 조금 부풀려 둥글게 만든다
        {
          type: "polygon",
          outline: [...[117, 118, 101, 36, 205, 187].map(at), between(123, 50, 0.4)],
        },
        {
          type: "polygon",
          outline: [...[346, 347, 330, 266, 425, 411].map(at), between(352, 280, 0.4)],
        },
        point(between(36, 205)),
        arrow(between(36, 205), between(50, 123, 0.4)),
        point(between(266, 425)),
        arrow(between(266, 425), between(280, 352, 0.4)),
      ],
    },
    {
      // 눈썹이 가늘어 윤곽선 대신 눈썹 두께만 한 띠로 보여 준다.
      // 윗선·아랫선의 가운데를 앞머리(55·107)에서 꼬리(46·70)까지
      stepId: "brow",
      title: "눈썹: 앞머리에서 꼬리 쪽으로 결대로 빈 곳만 채워요",
      regions: ["rightBrow", "leftBrow"],
      guides: [
        point(between(55, 107)),
        {
          type: "polyline",
          path: [
            between(55, 107),
            between(65, 66),
            between(52, 105),
            between(53, 63),
            between(46, 70),
          ],
          width: 0.08,
        },
        point(between(285, 336)),
        {
          type: "polyline",
          path: [
            between(285, 336),
            between(295, 296),
            between(282, 334),
            between(283, 293),
            between(276, 300),
          ],
          width: 0.08,
        },
      ],
    },
    {
      // 윗눈꺼풀 ~ 눈썹까지의 아래쪽 40% (쌍꺼풀 라인 높이)
      stepId: "eyeshadow",
      title: "아이섀도: 쌍꺼풀 라인 높이까지 안쪽에서 바깥쪽으로 펴 발라요",
      regions: ["rightEye", "leftEye"],
      guides: [
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
      ],
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
      // 윗눈꺼풀(속눈썹 뿌리) 가운데·바깥쪽에서 눈썹 쪽으로. 화살이 짧아 많으면 화살촉끼리 겹친다
      stepId: "mascara",
      title: "마스카라: 속눈썹 뿌리에서 위로 쓸어 올려요",
      regions: ["rightEye", "leftEye"],
      guides: [
        arrow(at(159), between(159, 52, 0.7)),
        arrow(at(161), between(161, 46, 0.7)),
        arrow(at(386), between(386, 282, 0.7)),
        arrow(at(388), between(388, 276, 0.7)),
      ],
    },
    {
      stepId: "lip",
      title: "립: 입술 안쪽에 바르고 바깥쪽으로 톡톡 펴 그라데이션해요",
      regions: ["lipsOuter"],
      guides: [
        outline(regions.lipsOuter.indices),
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
