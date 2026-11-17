import type { NormalizedRect, Point, ViewTransform } from "./types";

type Size = { width: number; height: number };

/** 영상을 컨테이너에 꽉 채워(object-fit: cover) 가운데 정렬할 때의 변환 */
export function coverTransform(video: Size, container: Size, mirrored: boolean): ViewTransform {
  const scale = Math.max(container.width / video.width, container.height / video.height);
  return {
    scale,
    offsetX: (container.width - video.width * scale) / 2,
    offsetY: (container.height - video.height * scale) / 2,
    mirrored,
  };
}

/** 영상 전체를 컨테이너 안에 넣어(object-fit: contain) 가운데 정렬할 때의 변환 */
export function containTransform(video: Size, container: Size, mirrored: boolean): ViewTransform {
  const scale = Math.min(container.width / video.width, container.height / video.height);
  return {
    scale,
    offsetX: (container.width - video.width * scale) / 2,
    offsetY: (container.height - video.height * scale) / 2,
    mirrored,
  };
}

/**
 * 얼굴 점들이 컨테이너의 fill 비율을 채우도록 확대해 가운데 둘 때의 변환 (거울 방향).
 * 영상을 숨기고 가이드만 띄우는 화면에서 얼굴을 크게 보여 줄 때 쓴다.
 */
export function faceFitTransform(
  points: readonly Point[],
  image: Size,
  container: Size,
  fill: number,
): ViewTransform {
  const xs = points.map((p) => (1 - p.x) * image.width);
  const ys = points.map((p) => p.y * image.height);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale =
    fill *
    Math.min(container.width / Math.max(1, x1 - x0), container.height / Math.max(1, y1 - y0));
  return {
    scale,
    offsetX: container.width / 2 - ((x0 + x1) / 2) * scale,
    offsetY: container.height / 2 - ((y0 + y1) / 2) * scale,
    mirrored: true,
  };
}

/** 컨테이너 가운데에 오는 점은 그대로 두고 배율만 scale로 바꾼 변환 */
export function rescaleAround(view: ViewTransform, scale: number, container: Size): ViewTransform {
  const k = scale / view.scale;
  const [cx, cy] = [container.width / 2, container.height / 2];
  return {
    scale,
    offsetX: cx - (cx - view.offsetX) * k,
    offsetY: cy - (cy - view.offsetY) * k,
    mirrored: view.mirrored,
  };
}

/** 화면(container)에 실제로 보이는 원본 프레임 영역. cover면 잘린 부분이 빠지고, contain이면 프레임 전체다. */
export function visibleRect(image: Size, container: Size, view: ViewTransform): NormalizedRect {
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  const toX = (sx: number) => (sx - view.offsetX) / (image.width * view.scale);
  const toY = (sy: number) => (sy - view.offsetY) / (image.height * view.scale);
  let [x0, x1] = [toX(0), toX(container.width)];
  if (view.mirrored) [x0, x1] = [1 - x1, 1 - x0];
  return { x0: clamp(x0), y0: clamp(toY(0)), x1: clamp(x1), y1: clamp(toY(container.height)) };
}

/** 정규화 좌표를 화면 픽셀 좌표로 바꾼다. */
export function toScreen(p: Point, image: Size, view: ViewTransform) {
  const x = view.mirrored ? 1 - p.x : p.x;
  return {
    x: x * image.width * view.scale + view.offsetX,
    y: p.y * image.height * view.scale + view.offsetY,
  };
}
