import type { Point, ViewTransform } from "./types";

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

/** 정규화 좌표를 화면 픽셀 좌표로 바꾼다. */
export function toScreen(p: Point, image: Size, view: ViewTransform) {
  const x = view.mirrored ? 1 - p.x : p.x;
  return {
    x: x * image.width * view.scale + view.offsetX,
    y: p.y * image.height * view.scale + view.offsetY,
  };
}
