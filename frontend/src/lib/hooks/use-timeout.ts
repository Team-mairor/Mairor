"use client";

import { useEffect, useMemo, useRef } from "react";

/** 타이머 하나. set은 앞서 건 것을 취소하고 새로 걸며, 컴포넌트가 사라지면 저절로 취소된다 */
export function useTimeout() {
  const ref = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => clearTimeout(ref.current), []);
  return useMemo(
    () => ({
      set(fn: () => void, ms: number) {
        clearTimeout(ref.current);
        ref.current = setTimeout(fn, ms);
      },
      clear() {
        clearTimeout(ref.current);
      },
    }),
    [],
  );
}
