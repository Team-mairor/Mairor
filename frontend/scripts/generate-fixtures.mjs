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
// 추적기와 같은 판정 기준을 그대로 쓴다. 값을 바꾸면 픽스처를 다시 생성한다.
const { MIN_IN_FRAME_RATIO } = await import("../src/features/face/visibility.ts");
const { DEFAULT_MAX_YAW: MAX_YAW, KEY_REGIONS } =
  await import("../src/features/face/tracking-rules.ts");

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
  const degraded = KEY_REGIONS.some(
    (name) =>
      regionVisibility[name].inFrameRatio < MIN_IN_FRAME_RATIO || !regionVisibility[name].facing,
  );

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
const uvPt = (i) => ({ x: uv[i][0], y: uv[i][1] });

function barycentric(p, [a, b, c]) {
  const v0 = { x: b.x - a.x, y: b.y - a.y };
  const v1 = { x: c.x - a.x, y: c.y - a.y };
  const v2 = { x: p.x - a.x, y: p.y - a.y };
  const det = v0.x * v1.y - v1.x * v0.y;
  const wb = (v2.x * v1.y - v1.x * v2.y) / det;
  const wc = (v0.x * v2.y - v2.x * v0.y) / det;
  return [1 - wb - wc, wb, wc];
}

/** UV 위의 점을 가장 알맞은 삼각형 기준 MeshAnchor로 바꾼다. 삼각형 밖이면 가장 가까운 삼각형 (음수 비율) */
function anchorAt(p) {
  let best = null;
  triangles.forEach((tri, index) => {
    const bary = barycentric(
      p,
      tri.map((i) => uvPt(i)),
    );
    const outside = -Math.min(...bary);
    if (!best || outside < best.outside) best = { index, bary, outside };
  });
  const bary = best.bary.map((v) => round(v));
  bary[0] = round(1 - bary[1] - bary[2]);
  return { triangle: best.index, bary };
}

// 아이라인: 눈 안쪽 1/3 지점에서 눈꼬리까지 속눈썹 라인을 따라가고, 꼬리는 아래 속눈썹 라인의 연장선에서
// 눈썹 꼬리 쪽으로 살짝 올려 뺀다. MediaPipe 윗눈꺼풀 점은 눈꺼풀 가장자리라, 선이 눈꺼풀 위로 뜨지 않게
// 아래 눈꺼풀 쪽으로 조금 내린다.
const LASH_LINE_SHIFT = 0.12; // 눈 뜬 높이 대비
const WING_LENGTH = 0.3; // 눈 너비 대비
const WING_LIFT = 0.25; // 눈썹 꼬리 방향을 섞는 비율

const unit = (v) => {
  const len = Math.hypot(v.x, v.y) || 1;
  return { x: v.x / len, y: v.y / len };
};

function eyelinerPath({ upper, lower, lowerNearOuter, inner, outer, browTail }) {
  const path = upper.map((i, k) => {
    const u = uvPt(i);
    const l = uvPt(lower[k]);
    return anchorAt({
      x: u.x + (l.x - u.x) * LASH_LINE_SHIFT,
      y: u.y + (l.y - u.y) * LASH_LINE_SHIFT,
    });
  });
  const corner = uvPt(outer);
  const along = unit({
    x: corner.x - uvPt(lowerNearOuter).x,
    y: corner.y - uvPt(lowerNearOuter).y,
  });
  const toBrow = unit({ x: uvPt(browTail).x - corner.x, y: uvPt(browTail).y - corner.y });
  const dir = unit({ x: along.x + toBrow.x * WING_LIFT, y: along.y + toBrow.y * WING_LIFT });
  const length = Math.hypot(corner.x - uvPt(inner).x, corner.y - uvPt(inner).y) * WING_LENGTH;
  path.push(anchorAt({ x: corner.x + dir.x * length, y: corner.y + dir.y * length }));
  return path;
}

// 윗눈꺼풀과 같은 자리의 아래 눈꺼풀 점 (안쪽 1/3 → 눈꼬리 직전). 눈꼬리 점은 아래로 꺾여 있어 건너뛴다
const RIGHT_EYELINER = {
  upper: [157, 158, 159, 160, 161, 246],
  lower: [154, 153, 145, 144, 163, 7],
  lowerNearOuter: 163,
  inner: 133,
  outer: 33,
  browTail: 46,
};
const LEFT_EYELINER = {
  upper: [384, 385, 386, 387, 388, 466],
  lower: [381, 380, 374, 373, 390, 249],
  lowerNearOuter: 390,
  inner: 362,
  outer: 263,
  browTail: 276,
};

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

// 블러셔: 볼 후보 영역을 넓게 흐린다.
{
  const { mask } = polygonMask([REGIONS.rightCheek.indices, REGIONS.leftCheek.indices]);
  writePng(
    "layers/masks/blush.png",
    blur(mask, 10).map((v) => Math.min(1, v * 1.4)),
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
    path: eyelinerPath(RIGHT_EYELINER),
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
    path: eyelinerPath(LEFT_EYELINER),
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
    opacity: 0.35,
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
const at = (i) => anchorAt(uvPt(i));
const between = (i, j, t = 0.5) =>
  anchorAt({ x: uv[i][0] + (uv[j][0] - uv[i][0]) * t, y: uv[i][1] + (uv[j][1] - uv[i][1]) * t });
const outline = (indices) => ({ type: "polygon", outline: indices.map(at) });

// 아이섀도: 윗눈꺼풀 ~ 눈썹 아래선 사이 영역, 안쪽에서 바깥쪽으로 펴 바르기
const shadowRight = [33, 246, 161, 160, 159, 158, 157, 173, 133, 55, 65, 52, 53, 46];
const shadowLeft = [263, 466, 388, 387, 386, 385, 384, 398, 362, 285, 295, 282, 283, 276];
// 블러셔: 볼 가운데에서 관자놀이 쪽으로 쓸어 올리기
// 볼 점 번호는 후보값이라 안쪽 점이 섞여 있어, 바깥 테두리 점만 이은 모양을 쓴다.
const cheekHull = {
  right: [116, 117, 118, 101, 36, 207, 147],
  left: [266, 330, 347, 346, 345, 376, 427],
};
const cheekCenter = { right: between(50, 117), left: between(280, 346) };

const guideSteps = [
  {
    stepId: "g1",
    source: "template",
    order: 1,
    title: "아이섀도: 눈두덩 전체에 안쪽에서 바깥쪽으로 펴 발라요",
    regions: ["rightEye", "leftEye"],
    guides: [
      outline(shadowRight),
      outline(shadowLeft),
      { type: "arrow", from: between(159, 65, 0.3), to: between(33, 46, 0.6) },
      { type: "arrow", from: between(386, 295, 0.3), to: between(263, 276, 0.6) },
    ],
  },
  {
    stepId: "g2",
    source: "template",
    order: 2,
    title: "아이라인: 속눈썹 라인을 따라 그리고 꼬리를 살짝 올려요",
    regions: ["rightEye", "leftEye"],
    guides: [
      { type: "point", at: eyelinerPath(RIGHT_EYELINER)[0] },
      { type: "polyline", path: eyelinerPath(RIGHT_EYELINER), width: 0.03 },
      { type: "point", at: eyelinerPath(LEFT_EYELINER)[0] },
      { type: "polyline", path: eyelinerPath(LEFT_EYELINER), width: 0.03 },
    ],
  },
  {
    stepId: "g3",
    source: "template",
    order: 3,
    title: "블러셔: 볼 가운데에서 관자놀이 쪽으로 쓸어 올려요",
    regions: ["rightCheek", "leftCheek"],
    guides: [
      outline(cheekHull.right),
      outline(cheekHull.left),
      { type: "point", at: cheekCenter.right },
      { type: "arrow", from: cheekCenter.right, to: between(117, 127, 0.7) },
      { type: "point", at: cheekCenter.left },
      { type: "arrow", from: cheekCenter.left, to: between(346, 356, 0.7) },
    ],
  },
  {
    stepId: "g4",
    source: "template",
    order: 4,
    title: "립: 입술 가운데에서 양쪽 끝으로 펴 발라요",
    regions: ["lipsOuter"],
    guides: [
      outline(REGIONS.lipsOuter.indices),
      { type: "point", at: between(0, 17) },
      { type: "arrow", from: between(0, 17), to: between(61, 0, 0.15) },
      { type: "arrow", from: between(0, 17), to: between(291, 0, 0.15) },
    ],
  },
];
writeJson("guides/sample.json", { meshVersion: "v1", steps: guideSteps });
writeJson("guides/empty.json", { meshVersion: "v1", steps: [] });

console.log(`[generate-fixtures] ${outDir}에 픽스처를 만들었습니다.`);
