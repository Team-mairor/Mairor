import {
  MIN_IN_FRAME_RATIO,
  regionNamesError,
  type FaceFrame,
  type RegionName,
} from "@/vision/face";

import { anchorError, MESH_VERSION, type FaceMesh } from "./mesh";
import type { LayerSet, MakeupLayer } from "./types";

export const UV_MASK_SIZE = 512;

export interface UvMask {
  /** 흰색 + 마스크 밝기를 알파로 바꾼 이미지 */
  image: HTMLCanvasElement;
  /** 마스크 값이 있는 삼각형만 그린다 */
  triangles: number[];
  /** 삼각형별 꼭짓점 UV (0~1) */
  uv: { x: number; y: number }[][];
}

export interface PreparedLayer {
  layer: MakeupLayer;
  mask: UvMask | null;
}

async function loadImage(url: string): Promise<HTMLImageElement> {
  const image = new Image();
  image.src = url;
  await image.decode();
  return image;
}

async function loadUvMask(url: string, mesh: FaceMesh): Promise<UvMask> {
  const image = await loadImage(url);
  if (image.naturalWidth !== UV_MASK_SIZE || image.naturalHeight !== UV_MASK_SIZE) {
    throw new Error(`UV 마스크 크기가 ${UV_MASK_SIZE}×${UV_MASK_SIZE}가 아닙니다: ${url}`);
  }

  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = UV_MASK_SIZE;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(image, 0, 0);
  const pixels = ctx.getImageData(0, 0, UV_MASK_SIZE, UV_MASK_SIZE);
  const data = pixels.data;
  for (let i = 0; i < data.length; i += 4) {
    data[i + 3] = data[i];
    data[i] = data[i + 1] = data[i + 2] = 255;
  }
  ctx.putImageData(pixels, 0, 0);

  const triangles: number[] = [];
  mesh.triangles.forEach((tri, index) => {
    const us = tri.map((i) => mesh.uv[i][0] * UV_MASK_SIZE);
    const vs = tri.map((i) => mesh.uv[i][1] * UV_MASK_SIZE);
    const x0 = Math.max(0, Math.floor(Math.min(...us)));
    const x1 = Math.min(UV_MASK_SIZE - 1, Math.ceil(Math.max(...us)));
    const y0 = Math.max(0, Math.floor(Math.min(...vs)));
    const y1 = Math.min(UV_MASK_SIZE - 1, Math.ceil(Math.max(...vs)));
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        if (data[(y * UV_MASK_SIZE + x) * 4 + 3] > 0) {
          triangles.push(index);
          return;
        }
      }
    }
  });

  const uv = triangles.map((t) =>
    mesh.triangles[t].map((i) => ({ x: mesh.uv[i][0], y: mesh.uv[i][1] })),
  );
  return { image: canvas, triangles, uv };
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i;

const isSize = (value: unknown) =>
  value === undefined || (typeof value === "number" && Number.isFinite(value) && value >= 0);

/** 그릴 수 없는 값이면 이유를 돌려준다. */
function invalidReason(layer: MakeupLayer, mesh: FaceMesh): string | null {
  const regionError =
    regionNamesError(layer.regions) ??
    (layer.exclude === undefined ? null : regionNamesError(layer.exclude, { allowEmpty: true }));
  if (regionError) return regionError;
  if (!isSize(layer.width) || !isSize(layer.feather)) {
    return `width·feather는 0 이상의 숫자여야 합니다: ${layer.width}, ${layer.feather}`;
  }
  if (layer.color !== null && !HEX_COLOR.test(layer.color)) return `색 형식 오류: ${layer.color}`;
  if (typeof layer.opacity !== "number" || !Number.isFinite(layer.opacity)) {
    return `opacity 없음: ${layer.opacity}`;
  }
  if (layer.shape === "polyline") {
    if (!(layer.path?.length && layer.width)) return "polyline에 path·width 없음";
    for (const anchor of layer.path) {
      const error = anchorError(anchor, mesh);
      if (error) return error;
    }
  }
  if (layer.shape === "uvMask" && !layer.uvMask) return "uvMask 경로 없음";
  return null;
}

/** 레이어 파일을 불러와 그릴 준비를 한다. 그릴 수 없는 레이어는 경고만 남기고 뺀다. */
export async function loadLayerSet(url: string, mesh: FaceMesh): Promise<PreparedLayer[]> {
  const response = await fetch(url);
  if (!response.ok)
    throw new Error(`레이어 파일을 불러오지 못했습니다: ${url} (${response.status})`);
  const set = (await response.json()) as LayerSet;
  // 다른 번호표 기준이면 모든 위치가 어긋나므로 통째로 쓰지 않는다.
  if (set.meshVersion !== MESH_VERSION) {
    throw new Error(
      `레이어 파일의 meshVersion(${set.meshVersion})이 ${MESH_VERSION}이 아닙니다: ${url}`,
    );
  }
  const base = new URL(url, window.location.href);

  const prepared = await Promise.all(
    set.layers.map(async (layer): Promise<PreparedLayer | null> => {
      const reason = invalidReason(layer, mesh);
      if (reason) {
        console.warn(`${layer.stepId} 레이어를 그릴 수 없어 뺍니다: ${reason}`);
        return null;
      }
      if (!layer.color) return null;
      if (layer.shape !== "uvMask") return { layer, mask: null };
      try {
        return { layer, mask: await loadUvMask(new URL(layer.uvMask!, base).href, mesh) };
      } catch (e) {
        console.warn(`${layer.stepId} 레이어의 UV 마스크를 쓸 수 없어 뺍니다`, e);
        return null;
      }
    }),
  );
  return prepared.filter((p) => p !== null);
}

export function isRegionInFrame(frame: FaceFrame, region: RegionName) {
  return frame.regionVisibility[region].inFrameRatio >= MIN_IN_FRAME_RATIO;
}

/**
 * 부위가 모두 화면 밖이면 그리지 않는다. 추적 상태(불안정·놓침)는 렌더러가 공용 규칙으로 먼저 거른다.
 * 고개를 돌린 정도는 렌더러가 진하기로 서서히 반영한다.
 */
export function isLayerVisible(layer: MakeupLayer, frame: FaceFrame | null): boolean {
  if (!frame || frame.trackingState === "lost") return false;
  // 얼굴 전체(faceOval)는 메시로 칠해 화면 밖 부분이 알아서 빠지므로 숨기지 않는다.
  return layer.regions.some((region) => region === "faceOval" || isRegionInFrame(frame, region));
}
