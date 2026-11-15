// 미리보기·추적 확인용 픽스처(public/fixtures/)를 캐노니컬 얼굴 메시로 만든다.
//   npm run fixtures
// .ts 파일을 바로 import하고 zlib.crc32를 쓰므로 Node 22.18 이상이 필요하다.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// 버전이 낮으면 아래 import에서 알기 어려운 오류가 나므로 먼저 확인한다.
const [major, minor] = process.versions.node.split(".").map(Number);
if (major < 22 || (major === 22 && minor < 18)) {
  console.error(`[generate-fixtures] Node 22.18 이상이 필요합니다 (지금 ${process.versions.node})`);
  process.exit(1);
}
const { crc32, deflateSync } = await import("node:zlib");
const { REGIONS } = await import("../src/features/face/regions.ts");
const { anchorTools, buildDefaultGuideSet, eyelinerPaths } =
  await import("../src/features/guide/default-guides.ts");
// 추적기와 같은 판정 기준을 그대로 쓴다. 값을 바꾸면 픽스처를 다시 생성한다.
const { MIN_IN_FRAME_RATIO } = await import("../src/features/face/visibility.ts");
const {
  DEFAULT_MAX_YAW: MAX_YAW,
  KEY_REGIONS,
  MIN_KEY_REGIONS_IN_VIEW,
} = await import("../src/features/face/tracking-rules.ts");

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const meshDir = join(frontendDir, "../shared/face-mesh");
const outDir = join(frontendDir, "public/fixtures");

const { triangles } = JSON.parse(readFileSync(join(meshDir, "triangles.v1.json"), "utf8"));
const { uv } = JSON.parse(readFileSync(join(meshDir, "uv.v1.json"), "utf8"));

const round = (v, digits = 4) => Number(v.toFixed(digits));

function writeJson(path, body) {
  const file = join(outDir, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, JSON.stringify(body, null, 2) + "\n");
}

// ── 얼굴 ──
// 캐노니컬 UV는 정면 얼굴을 펼친 좌표라, 화면 위 정면 얼굴 랜드마크로 그대로 쓸 수 있다.
const IMAGE = { width: 1280, height: 720 };
const RIGHT_IRIS = 468;
const LEFT_IRIS = 473;

function faceLandmarks({ scale = 1, offsetX = 0, offsetY = 0 } = {}) {
  // 얼굴 높이가 화면 높이의 약 75%가 되도록 놓는다 (가로·세로 픽셀 비율 유지)
  const size = IMAGE.height * 0.9 * scale;
  const cx = IMAGE.width / 2 + offsetX;
  const cy = IMAGE.height / 2 + offsetY;
  const toPoint = ([u, v]) => ({
    x: round((cx + (u - 0.5) * size) / IMAGE.width),
    y: round((cy + (v - 0.53) * size) / IMAGE.height),
    z: 0,
  });
  const points = uv.map(toPoint);

  // 홍채(468~477)는 메시에 없어 눈 가운데에 둔다: 중심 1개 + 상하좌우 4개
  const iris = (outer, inner, top, bottom) => {
    const c = {
      x: (points[outer].x + points[inner].x) / 2,
      y: (points[top].y + points[bottom].y) / 2,
    };
    const r = Math.abs(points[outer].x - points[inner].x) * 0.22;
    const ry = (r * IMAGE.width) / IMAGE.height;
    return [
      c,
      { x: c.x + r, y: c.y },
      { x: c.x, y: c.y - ry },
      { x: c.x - r, y: c.y },
      { x: c.x, y: c.y + ry },
    ].map((p) => ({ x: round(p.x), y: round(p.y), z: 0 }));
  };
  points.push(...iris(33, 133, 159, 145), ...iris(263, 362, 386, 374));
  return points;
}

const px = (p) => ({ x: p.x * IMAGE.width, y: p.y * IMAGE.height });

// features/face/geometry.ts의 computeRegion과 같은 계산
function region(name, landmarks, iod) {
  const { indices, axis } = REGIONS[name];
  const points = indices.map((i) => landmarks[i]);
  const center = {
    x: round(points.reduce((s, p) => s + p.x, 0) / points.length),
    y: round(points.reduce((s, p) => s + p.y, 0) / points.length),
  };
  const a = px(landmarks[axis[0]]);
  const b = px(landmarks[axis[1]]);
  const angle = Math.atan2(b.y - a.y, b.x - a.x);
  const ux = Math.cos(angle);
  const uy = Math.sin(angle);
  const us = points.map((p) => px(p).x * ux + px(p).y * uy);
  const vs = points.map((p) => -px(p).x * uy + px(p).y * ux);
  return {
    indices: [...indices],
    center,
    width: round((Math.max(...us) - Math.min(...us)) / iod),
    height: round((Math.max(...vs) - Math.min(...vs)) / iod),
    angle: round(angle),
  };
}

// 근접 축소 배율에 따른 degraded는 픽스처가 축소 없이 만든 프레임이라 다루지 않는다.
/** trackingState를 주지 않으면 추적기와 같은 규칙으로 tracking·degraded를 정한다. */
function faceFrame({ trackingState, yaw = 0, placement, eyes } = {}) {
  const landmarks = faceLandmarks(placement);
  const r = px(landmarks[RIGHT_IRIS]);
  const l = px(landmarks[LEFT_IRIS]);
  const iod = Math.hypot(l.x - r.x, l.y - r.y);
  const maxYaw = MAX_YAW;

  const regions = {};
  const regionVisibility = {};
  for (const [name, def] of Object.entries(REGIONS)) {
    regions[name] = region(name, landmarks, iod);
    const inFrame = def.indices.filter((i) => {
      const p = landmarks[i];
      return p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1;
    }).length;
    const facing =
      def.side === "left"
        ? yaw < maxYaw
        : def.side === "right"
          ? yaw > -maxYaw
          : Math.abs(yaw) < maxYaw;
    regionVisibility[name] = { inFrameRatio: round(inFrame / def.indices.length, 3), facing };
  }
  const inView = KEY_REGIONS.filter(
    (name) =>
      regionVisibility[name].inFrameRatio >= MIN_IN_FRAME_RATIO && regionVisibility[name].facing,
  ).length;
  const degraded = inView < MIN_KEY_REGIONS_IN_VIEW;

  return {
    version: "0.2",
    meshVersion: "v1",
    timestamp: 0,
    imageSize: IMAGE,
    trackingState: trackingState ?? (degraded ? "degraded" : "tracking"),
    landmarks,
    iod: round(iod, 2),
    pose: { yaw, pitch: 0, roll: 0 },
    eyes: eyes ?? {
      left: { openness: 1, blinking: false },
      right: { openness: 1, blinking: false },
    },
    regions,
    regionVisibility,
  };
}

writeJson("faces/front.json", faceFrame());
// 랜드마크는 정면 그대로 두고 방향 값만 바꿔, 왼쪽 부위가 가려진 상태를 만든다.
writeJson("faces/turned-left.json", faceFrame({ yaw: 0.8 }));
writeJson("faces/close-up.json", faceFrame({ placement: { scale: 1.6, offsetY: 160 } }));
// 멀리: 얼굴 폭이 화면의 약 30%로 '조금 더 가까이' 안내 기준(40%)보다 작지만 추적은 된다
writeJson("faces/far.json", faceFrame({ placement: { scale: 0.45 } }));
writeJson(
  "faces/blink-hold.json",
  faceFrame({
    trackingState: "hold",
    eyes: {
      left: { openness: 0, blinking: true },
      right: { openness: 0, blinking: true },
    },
  }),
);
writeJson("faces/lost.json", faceFrame({ trackingState: "lost" }));

// ── 아이라인 경로 (MeshAnchor) ──
// 기본 가이드와 같은 경로를 레이어에도 쓴다.
const eyeliner = eyelinerPaths({ triangles, uv });

// ── UV 마스크 ──
const SIZE = 512;

function polygonMask(polys, holes = []) {
  const mask = new Float32Array(SIZE * SIZE);
  const inside = (x, y, poly) => {
    let hit = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const a = poly[i];
      const b = poly[j];
      if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
    }
    return hit;
  };
  const toPx = (poly) => poly.map((i) => ({ x: uv[i][0] * SIZE, y: uv[i][1] * SIZE }));
  const fills = polys.map(toPx);
  const cuts = holes.map(toPx);
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      const p = { x: x + 0.5, y: y + 0.5 };
      if (fills.some((f) => inside(p.x, p.y, f)) && !cuts.some((c) => inside(p.x, p.y, c))) {
        mask[y * SIZE + x] = 1;
      }
    }
  }
  return { mask, cuts, inside };
}

function blur(mask, radius) {
  // 상자 흐림 세 번 ≈ 가우시안
  let src = mask;
  for (let pass = 0; pass < 3; pass++) {
    for (const horizontal of [true, false]) {
      const out = new Float32Array(SIZE * SIZE);
      for (let y = 0; y < SIZE; y++) {
        for (let x = 0; x < SIZE; x++) {
          let sum = 0;
          let n = 0;
          for (let k = -radius; k <= radius; k++) {
            const xx = horizontal ? x + k : x;
            const yy = horizontal ? y : y + k;
            if (xx < 0 || yy < 0 || xx >= SIZE || yy >= SIZE) continue;
            sum += src[yy * SIZE + xx];
            n++;
          }
          out[y * SIZE + x] = sum / n;
        }
      }
      src = out;
    }
  }
  return src;
}

// 8비트 흑백 PNG (색 프로필 없음)
function writePng(path, values) {
  const raw = Buffer.alloc((SIZE + 1) * SIZE);
  for (let y = 0; y < SIZE; y++) {
    raw[y * (SIZE + 1)] = 0;
    for (let x = 0; x < SIZE; x++) {
      raw[y * (SIZE + 1) + 1 + x] = Math.round(
        Math.max(0, Math.min(1, values[y * SIZE + x])) * 255,
      );
    }
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(body));
    return Buffer.concat([len, body, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(SIZE, 0);
  ihdr.writeUInt32BE(SIZE, 4);
  ihdr[8] = 8; // 비트 깊이
  ihdr[9] = 0; // 흑백
  const png = Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
  const file = join(outDir, path);
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, png);
}

// 아이섀도: 윗눈꺼풀 ~ 눈썹 아래선 사이. 흐린 뒤 눈 안쪽과 눈썹은 다시 0으로 둔다 (번져 물들지 않게).
{
  const right = [33, 246, 161, 160, 159, 158, 157, 173, 133, 55, 65, 52, 53, 46];
  const left = [263, 466, 388, 387, 386, 385, 384, 398, 362, 285, 295, 282, 283, 276];
  const cutRegions = ["rightEye", "leftEye", "rightBrow", "leftBrow"].map(
    (r) => REGIONS[r].indices,
  );
  const { mask, cuts, inside } = polygonMask([right, left], cutRegions);
  const soft = blur(mask, 6);
  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      if (cuts.some((c) => inside(x + 0.5, y + 0.5, c))) soft[y * SIZE + x] = 0;
    }
  }
  writePng("layers/masks/eyeshadow.png", soft);
}

// 블러셔: 튜토리얼 가이드와 같은 볼 영역 전체를 크게 흐려, 경계 없이 바깥으로 옅어지게 한다.
{
  const { mask } = polygonMask([REGIONS.rightCheek.indices, REGIONS.leftCheek.indices]);
  writePng(
    "layers/masks/blush.png",
    blur(mask, 24).map((v) => {
      const t = Math.min(1, v * 1.2);
      return t * t * (3 - 2 * t);
    }),
  );
}

// ── 레이어 ──
const base = { colorSource: "manual", source: "manual" };
const layers = {
  foundation: {
    stepId: "s1",
    makeup: "foundation",
    regions: ["faceOval"],
    exclude: ["leftEye", "rightEye", "leftBrow", "rightBrow", "lipsOuter"],
    shape: "polygon",
    feather: 0.08,
    color: "#E8C4A8",
    opacity: 0.3,
    blend: "normal",
    ...base,
  },
  eyeshadow: {
    stepId: "s2",
    makeup: "eyeshadow",
    regions: ["leftEye", "rightEye"],
    shape: "uvMask",
    uvMask: "masks/eyeshadow.png",
    color: "#B07A6A",
    opacity: 0.5,
    blend: "multiply",
    ...base,
  },
  eyelinerRight: {
    stepId: "s3",
    makeup: "eyeliner",
    regions: ["rightEye"],
    shape: "polyline",
    path: eyeliner.right,
    width: 0.03,
    feather: 0.01,
    lineCap: "round",
    color: "#2B1D1A",
    opacity: 0.8,
    blend: "normal",
    ...base,
  },
  eyelinerLeft: {
    stepId: "s3",
    makeup: "eyeliner",
    regions: ["leftEye"],
    shape: "polyline",
    path: eyeliner.left,
    width: 0.03,
    feather: 0.01,
    lineCap: "round",
    color: "#2B1D1A",
    opacity: 0.8,
    blend: "normal",
    ...base,
  },
  blush: {
    stepId: "s4",
    makeup: "blush",
    regions: ["leftCheek", "rightCheek"],
    shape: "uvMask",
    uvMask: "masks/blush.png",
    color: "#F4A6A6",
    opacity: 0.15,
    blend: "multiply",
    ...base,
  },
  lip: {
    stepId: "s5",
    makeup: "lip",
    regions: ["lipsOuter"],
    exclude: ["lipsInner"],
    shape: "polygon",
    feather: 0.04,
    color: "#D65A70",
    opacity: 0.6,
    blend: "multiply",
    ...base,
  },
};

const set = (list) => ({ videoId: "fixture", meshVersion: "v1", layers: list });
const all = Object.values(layers);

writeJson("layers/sample.json", set(all));
writeJson("layers/lip-only.json", set([layers.lip]));
writeJson("layers/empty.json", set([]));
writeJson("layers/no-color.json", set([layers.foundation, { ...layers.lip, color: null }]));
writeJson(
  "layers/missing-mask.json",
  set([{ ...layers.blush, uvMask: "masks/not-found.png" }, layers.lip]),
);

// ── 튜토리얼 가이드 ──
// 앱의 기본 가이드(9개 부위)를 그대로 파일로 내보내, ?guides= 로 파일 불러오기를 확인한다.
const defaultGuides = buildDefaultGuideSet({ triangles, uv }, REGIONS);
writeJson("guides/sample.json", defaultGuides);
writeJson("guides/empty.json", { meshVersion: "v1", steps: [] });

// 좌우 확인용: 기본 가이드에서 본인 기준 오른쪽(UV x < 0.5) 도형만 남긴다.
// 거울 화면에서는 화면 오른쪽에 보여야 한다.
const anchorU = ({ triangle, bary }) =>
  triangles[triangle].reduce((sum, vertex, k) => sum + uv[vertex][0] * bary[k], 0);
const anchorsOf = (guide) =>
  guide.type === "point"
    ? [guide.at]
    : guide.type === "arrow"
      ? [guide.from, guide.to]
      : (guide.path ?? guide.outline);
const rightSteps = defaultGuides.steps
  .map((step) => ({
    ...step,
    regions: step.regions.filter((name) => name.startsWith("right")),
    guides: step.guides.filter((guide) => anchorsOf(guide).every((a) => anchorU(a) < 0.5)),
  }))
  .filter((step) => step.regions.length > 0 && step.guides.length > 0)
  .map((step, i) => ({ ...step, order: i + 1 }));
writeJson("guides/right-only.json", { ...defaultGuides, steps: rightSteps });

// ── AI 가이드 영역 (shared/guide-area) ──
// 상태 네 가지와 하위 단계 전환, 빼는 영역을 한 파일에서 확인한다. ?area= 로 불러온다.
// 기준점은 랜드마크 점 그대로 둔다. 입 안은 UV에서 위아래 입술 삼각형이 겹쳐 좌표로 다시 찾으면 반대쪽에 붙는다.
const vertexAnchor = (i) => {
  const triangle = triangles.findIndex((tri) => tri.includes(i));
  const bary = [0, 0, 0];
  bary[triangles[triangle].indexOf(i)] = 1;
  return { triangle, bary };
};
// 눈과 눈두덩을 함께 덮는 눈 둘레 고리 (눈 밑 → 눈두덩). 눈(exclude)을 빼서 눈 안쪽이 비어 보이는지 본다
const EYE_RINGS = {
  rightEye: [226, 31, 228, 229, 230, 231, 232, 233, 244, 189, 221, 222, 223, 224, 225, 113],
  leftEye: [446, 261, 448, 449, 450, 451, 452, 453, 464, 413, 441, 442, 443, 444, 445, 342],
};
const ring = (indices) => indices.map(vertexAnchor);
/** 꼭짓점 a에서 b 쪽으로 t만큼 간 점. a와 b는 한 삼각형에 있어야 한다 */
const edgeAnchor = (a, b, t) => {
  const triangle = triangles.findIndex((tri) => tri.includes(a) && tri.includes(b));
  if (triangle < 0) throw new Error(`${a}와 ${b}가 한 삼각형에 없습니다`);
  const bary = [0, 0, 0];
  bary[triangles[triangle].indexOf(a)] = 1 - t;
  bary[triangles[triangle].indexOf(b)] = t;
  return { triangle, bary };
};
/** 윗눈꺼풀 선 점과 그 위 점 [선, 위] 쌍을 받아, 선에서 위쪽으로 얇게 올린 띠 */
const lidBand = (pairs, t) => [
  ...pairs.map(([lid]) => vertexAnchor(lid)),
  ...pairs.map(([lid, above]) => edgeAnchor(lid, above, t)).reverse(),
];
// 떨어져 그린 얇은 아이라인: 눈 하나에 앞머리 쪽 띠와 눈꼬리 띠 두 도형
const EYELINER_DEPTH = 0.35;
const EYELINER_BANDS = {
  rightEye: [
    [
      [133, 243],
      [173, 190],
      [157, 56],
      [158, 28],
      [159, 27],
    ],
    [
      [161, 30],
      [246, 247],
      [33, 130],
    ],
  ],
  leftEye: [
    [
      [362, 463],
      [398, 414],
      [384, 286],
      [385, 258],
      [386, 257],
    ],
    [
      [388, 260],
      [466, 467],
      [263, 359],
    ],
  ],
};
const areaSet = (region, outline, exclude) => ({
  region,
  source: "extracted",
  guides: [{ type: "polygon", outline }],
  ...(exclude ? { exclude } : {}),
});
const sub = (stepId, order, status, extra = {}) => ({
  subStepId: `${stepId}-${order}`,
  order,
  status,
  reasons: [],
  templateId: null,
  guideSets: [],
  ...extra,
});
const areaStep = (order, makeup, subSteps) => ({ stepId: `s${order}`, order, makeup, subSteps });
// 원래 눈썹(랜드마크 테두리)보다 조금 위로 그린 눈썹. 두께는 AI 눈썹 영역 실측(0.027)과 비슷하다
const { between } = anchorTools({ triangles, uv });
const drawnBrow = (lower, upper) => [
  ...lower.map((i, k) => between(i, upper[k], 0)),
  ...upper.map((j, k) => between(lower[k], j, 1.2)).reverse(),
];
writeJson("guide-areas/sample.json", {
  videoId: "fixture",
  meshVersion: "v1",
  steps: [
    areaStep(1, "other", [sub("s1", 1, "notApplicable")]),
    areaStep(2, "foundation", [
      sub("s2", 1, "template", { reasons: ["noUsableFrame"], templateId: "foundation" }),
    ]),
    areaStep(3, "eyeshadow", [
      sub("s3", 1, "extracted", {
        guideSets: [
          areaSet("rightEye", ring(EYE_RINGS.rightEye), ["rightEye"]),
          areaSet("leftEye", ring(EYE_RINGS.leftEye), ["leftEye"]),
        ],
      }),
    ]),
    areaStep(4, "lip", [
      sub("s4", 1, "extracted", {
        guideSets: [areaSet("lipsOuter", ring(REGIONS.lipsOuter.indices), ["lipsInner"])],
      }),
      sub("s4", 2, "template", { reasons: ["noUsableFrame"], templateId: "lip" }),
    ]),
    areaStep(5, "blush", [sub("s5", 1, "failed", { reasons: ["FRAME_UNREADABLE"] })]),
    areaStep(6, "eyeliner", [
      sub("s6", 1, "template", { reasons: ["noUsableFrame"], templateId: "eyeliner" }),
      sub("s6", 2, "extracted", {
        guideSets: Object.entries(EYELINER_BANDS).map(([region, bands]) => ({
          region,
          source: "extracted",
          guides: bands.map((band) => ({
            type: "polygon",
            outline: lidBand(band, EYELINER_DEPTH),
          })),
          exclude: [],
        })),
      }),
    ]),
    areaStep(7, "brow", [
      sub("s7", 1, "extracted", {
        guideSets: [
          areaSet("rightBrow", drawnBrow([55, 65, 52, 53, 46], [107, 66, 105, 63, 70])),
          areaSet("leftBrow", drawnBrow([285, 295, 282, 283, 276], [336, 296, 334, 293, 300])),
        ],
      }),
    ]),
  ],
});

// 목업 가이드(lib/mock-guide.ts)와 같은 AI 샘플 영상의 가이드 영역. 튜토리얼이 단계 ID로 찾는다.
// 샘플의 extracted 좌표는 형식을 보이기 위한 예시라, 같은 부위의 랜드마크 테두리로 바꿔 화면에서 알아볼 수 있게 한다.
// 하위 단계 전환을 보려고 아이섀도 단계(s10)는 눈두덩 → 기본 영역(위아래 · 위 · 아래) → 애교살 다섯 하위 단계로 나눈다.
// 애교살 띠: 아래 눈꺼풀(눈꼬리 → 눈앞머리) → 눈 밑 고리(눈앞머리 → 눈꼬리)
const UNDER_EYE = {
  rightEye: [33, 7, 163, 144, 145, 153, 154, 155, 133, 244, 233, 232, 231, 230, 229, 228, 31, 226],
  leftEye: [
    263, 249, 390, 373, 374, 380, 381, 382, 362, 464, 453, 452, 451, 450, 449, 448, 261, 446,
  ],
};
const eyeshadowSubSteps = [
  sub("s10", 1, "extracted", {
    guideSets: [
      areaSet("rightEye", ring(EYE_RINGS.rightEye), ["rightEye"]),
      areaSet("leftEye", ring(EYE_RINGS.leftEye), ["leftEye"]),
    ],
  }),
  sub("s10", 2, "template", { reasons: ["noUsableFrame"], templateId: "eyeshadow" }),
  sub("s10", 3, "template", { reasons: ["eyeshadowColorNotFound"], templateId: "eyeshadowUpper" }),
  sub("s10", 4, "template", { reasons: ["eyeshadowColorNotFound"], templateId: "eyeshadowUnder" }),
  sub("s10", 5, "extracted", {
    guideSets: [
      areaSet("rightEye", ring(UNDER_EYE.rightEye)),
      areaSet("leftEye", ring(UNDER_EYE.leftEye)),
    ],
  }),
];
const aiArea = JSON.parse(
  readFileSync(join(frontendDir, "../ai/samples/local_01/guide_area.json"), "utf8"),
);
writeJson("guide-areas/local_01.json", {
  ...aiArea,
  steps: aiArea.steps.map((step) => ({
    ...step,
    subSteps:
      step.stepId === "s10"
        ? eyeshadowSubSteps
        : step.subSteps.map((s) => ({
            ...s,
            guideSets: s.guideSets.map((set) => ({
              ...set,
              guides: set.guides.map((guide) =>
                guide.type === "polygon"
                  ? { type: "polygon", outline: ring(REGIONS[set.region].indices) }
                  : guide,
              ),
            })),
          })),
  })),
});

console.log(`[generate-fixtures] ${outDir}에 픽스처를 만들었습니다.`);
