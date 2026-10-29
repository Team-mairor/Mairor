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
