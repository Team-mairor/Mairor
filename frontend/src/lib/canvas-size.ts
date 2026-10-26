/**
 * 캔버스의 화면 크기나 화면 배율(devicePixelRatio)이 바뀔 때마다 알려 준다.
 * 크기 변화 없이 배율만 바뀌는 경우(다른 화면으로 옮김, 확대)도 잡는다. 정리 함수를 돌려준다.
 */
export function observeCanvasSize(
  canvas: HTMLCanvasElement,
  onResize: (width: number, height: number, dpr: number) => void,
): () => void {
  const resize = () =>
    onResize(canvas.clientWidth, canvas.clientHeight, window.devicePixelRatio || 1);
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);

  // 지금 배율에서 벗어나면 change가 한 번 오므로, 받을 때마다 새 배율로 다시 건다.
  let media: MediaQueryList | null = null;
  const onDprChange = () => {
    resize();
    watchDpr();
  };
  const watchDpr = () => {
    media?.removeEventListener("change", onDprChange);
    media = window.matchMedia(`(resolution: ${window.devicePixelRatio || 1}dppx)`);
    media.addEventListener("change", onDprChange);
  };
  watchDpr();

  return () => {
    observer.disconnect();
    media?.removeEventListener("change", onDprChange);
  };
}
