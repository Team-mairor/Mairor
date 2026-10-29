"use client";

import { useEffect, useState } from "react";

/** until(ms 시각)까지 남은 초. 매초 갱신하고 0이 되면 멈춘다 */
export function useCountdown(until: number | null) {
  const calc = () => (until ? Math.max(0, Math.ceil((until - Date.now()) / 1000)) : 0);
  const [left, setLeft] = useState(calc);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 기준 시각이 바뀌면 바로 다시 센다
    setLeft(calc());
    if (!until) return;
    const t = setInterval(() => {
      const l = calc();
      setLeft(l);
      if (l <= 0) clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- calc는 until에만 의존한다
  }, [until]);
  return left;
}
