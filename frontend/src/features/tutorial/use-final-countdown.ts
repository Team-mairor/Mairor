"use client";

import { useEffect, useRef, useState } from "react";

const SECONDS = 3;

/**
 * 마지막 사진 전 3초 카운트다운. 끝나면 onFire로 촬영을 시작한다.
 * interrupt 중 하나라도 true이면(카메라 문제·나가기 창 등) 카운트다운을 접는다.
 * 값이 하나 바뀔 때마다 다시 확인해, 이미 true인 상태에서 다른 값이 바뀌어도 놓치지 않는다
 */
export function useFinalCountdown({
  onFire,
  interrupt,
}: {
  onFire: () => void;
  interrupt: readonly boolean[];
}) {
  const [countdown, setCountdown] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = useRef(false);

  const clearTimer = () => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  };

  /** 카운트다운 중이었으면 접고 true를 돌려준다 */
  const cancel = () => {
    if (!active.current) return false;
    active.current = false;
    clearTimer();
    setCountdown(null);
    return true;
  };

  const start = () => {
    if (active.current) return;
    active.current = true;
    setCountdown(SECONDS);

    const tick = (remaining: number) => {
      timer.current = setTimeout(() => {
        if (!active.current) return;
        if (remaining > 1) {
          setCountdown(remaining - 1);
          tick(remaining - 1);
          return;
        }

        active.current = false;
        timer.current = null;
        setCountdown(null);
        onFire();
      }, 1000);
    };

    tick(SECONDS);
  };

  const interrupted = interrupt.some(Boolean);
  const flags = interrupt.map(Number).join("");
  useEffect(() => {
    if (!interrupted) return;
    active.current = false;
    clearTimer();
    const resetTimer = setTimeout(() => setCountdown(null), 0);
    return () => clearTimeout(resetTimer);
  }, [interrupted, flags]);

  useEffect(
    () => () => {
      active.current = false;
      clearTimer();
    },
    [],
  );

  return { countdown, start, cancel };
}
