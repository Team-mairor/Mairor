"use client";

import { useEffect, useSyncExternalStore } from "react";

const KEY = "mairor:gauge-debug";
const subscribe = () => () => {};
const read = () => sessionStorage.getItem(KEY) === "1";

/** 개발 도구에서 ?gauge를 한 번 붙이면 같은 탭의 화면 이동 뒤에도 디버그 값을 계속 띄운다 */
export function useGaugeDebug(requested: boolean) {
  const enabled = process.env.DEV_TOOLS === "1";
  const stored = useSyncExternalStore(subscribe, read, () => false);
  useEffect(() => {
    if (enabled && requested) sessionStorage.setItem(KEY, "1");
  }, [enabled, requested]);
  return enabled && (requested || stored);
}
