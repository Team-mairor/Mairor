// 부위 점 번호는 AI(Python)와 같이 쓰도록 shared/face-mesh/regions.v1.json에 둔다.
// 픽스처 생성 스크립트도 Node에서 바로 읽으므로 JSON은 import 속성을 붙여 가져온다.
import type { FaceFrame, RegionName } from "./types";
import shared from "../../../../shared/face-mesh/regions.v1.json" with { type: "json" };

export const RIGHT_IRIS_CENTER = 468;
export const LEFT_IRIS_CENTER = 473;

interface RegionDef {
  /** 외곽선을 따라 한 바퀴 도는 순서. 그대로 이으면 닫힌 도형이 된다. */
  indices: readonly number[];
  /** 각도 기준 [시작, 끝] */
  axis: readonly [number, number];
  side: "left" | "right" | "center";
}

const SIDES: readonly RegionDef["side"][] = ["left", "right", "center"];

// 공유 파일의 부위 이름은 RegionName과 정확히 같아야 한다.
const NAMES = {
  rightEye: true,
  leftEye: true,
  rightBrow: true,
  leftBrow: true,
  lipsOuter: true,
  lipsInner: true,
  rightCheek: true,
  leftCheek: true,
  faceOval: true,
} satisfies Record<RegionName, true>;

// 메시 꼭짓점은 0~467이다. 홍채(468~)는 메시에 없다.
const isMeshVertex = (i: number) => Number.isInteger(i) && i >= 0 && i < RIGHT_IRIS_CENTER;

/** 공유 파일의 한 부위를 확인해 RegionDef로 바꾼다. 형식이 틀리면 화면을 그리기 전에 알 수 있게 바로 멈춘다. */
function toRegionDef(name: string, region: { indices: number[]; axis: number[]; side: string }) {
  const side = SIDES.find((s) => s === region.side);
  if (
    !Object.hasOwn(NAMES, name) ||
    region.indices.length < 3 ||
    !region.indices.every(isMeshVertex) ||
    region.axis.length !== 2 ||
    !region.axis.every(isMeshVertex) ||
    !side
  ) {
    throw new Error(`regions.v1.json의 ${name} 형식이 맞지 않습니다`);
  }
  return {
    indices: region.indices,
    axis: [region.axis[0], region.axis[1]],
    side,
  } satisfies RegionDef;
}

const missing = Object.keys(NAMES).filter((name) => !Object.hasOwn(shared.regions, name));
if (missing.length > 0) {
  throw new Error(`regions.v1.json에 부위가 빠졌습니다: ${missing.join(", ")}`);
}

export const REGIONS = {} as Record<RegionName, RegionDef>;
for (const [name, region] of Object.entries(shared.regions)) {
  REGIONS[name as RegionName] = toRegionDef(name, region);
}

export const REGION_NAMES = Object.keys(REGIONS) as RegionName[];

/** 부위 이름 목록이 아니면 이유를 돌려준다. 없는 이름이 하나라도 있으면 그리는 중에 오류가 난다. */
export function regionNamesError(names: unknown, { allowEmpty = false } = {}): string | null {
  if (!Array.isArray(names)) return "부위 목록이 배열이 아닙니다";
  if (!allowEmpty && names.length === 0) return "부위 목록이 비어 있습니다";
  const unknown = names.find((name) => !(REGION_NAMES as unknown[]).includes(name));
  return unknown === undefined ? null : `없는 부위 이름입니다: ${String(unknown)}`;
}

/** 사진 안의 네모 (0~1, 좌우 반전한 사진 기준) */
export interface PhotoBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * 부위들을 넉넉히 감싸는 정사각형(픽셀 기준)을 좌우 반전한 사진 좌표로 돌려준다.
 * 부위가 없거나 얼굴 전체(faceOval)면 자를 곳이 없어 null.
 */
export function mirroredRegionBox(
  frame: Pick<FaceFrame, "landmarks" | "imageSize">,
  regions: readonly RegionName[],
  pad = 1.6,
): PhotoBox | null {
  if (!regions.length || regions.includes("faceOval")) return null;
  let [minX, minY, maxX, maxY] = [1, 1, 0, 0];
  for (const name of regions) {
    for (const i of REGIONS[name].indices) {
      const p = frame.landmarks[i];
      if (!p) continue;
      [minX, minY] = [Math.min(minX, p.x), Math.min(minY, p.y)];
      [maxX, maxY] = [Math.max(maxX, p.x), Math.max(maxY, p.y)];
    }
  }
  if (maxX <= minX || maxY <= minY) return null;
  const { width, height } = frame.imageSize;
  const side = Math.min(
    Math.max((maxX - minX) * width, (maxY - minY) * height) * pad,
    width,
    height,
  );
  const [w, h] = [side / width, side / height];
  // 가운데를 맞추고 사진 밖으로 나가면 안쪽으로 민다
  const place = (center: number, size: number) =>
    Math.min(Math.max(center - size / 2, 0), 1 - size);
  return { x: place(1 - (minX + maxX) / 2, w), y: place((minY + maxY) / 2, h), w, h };
}

/** 두 프레임 사이 얼굴 점의 평균 이동 거리를 눈 사이 거리 대비로 (0이면 그대로). 흔들림 없이 찍을 때를 고른다 */
export function landmarkMotion(
  prev: Pick<FaceFrame, "landmarks">,
  frame: Pick<FaceFrame, "landmarks" | "imageSize" | "iod">,
): number {
  const { width, height } = frame.imageSize;
  const n = Math.min(prev.landmarks.length, frame.landmarks.length);
  if (!n || !frame.iod) return Infinity;
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const [a, b] = [prev.landmarks[i], frame.landmarks[i]];
    sum += Math.hypot((b.x - a.x) * width, (b.y - a.y) * height);
  }
  return sum / n / frame.iod;
}
