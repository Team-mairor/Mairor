"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { isAbortError } from "@/lib/api";

/**
 * 화면의 요청을 하나씩 보낸다. 새 요청을 보내면 이전 요청을 취소하고, 화면을 떠나면 진행 중인 요청을 취소한다.
 * pending은 진행 중인 요청의 이름이고, 없으면 null이다.
 */
export function useRequest<K extends string>() {
  const [pending, setPending] = useState<K | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  /** 취소는 무시하고, 실패하면 fail에 넘긴다 */
  const run = useCallback(
    async (kind: K, req: (signal: AbortSignal) => Promise<void>, fail: (e: unknown) => void) => {
      controller.current?.abort();
      const c = new AbortController();
      controller.current = c;
      setPending(kind);
      try {
        await req(c.signal);
      } catch (e) {
        if (!isAbortError(e)) fail(e);
      }
      if (!c.signal.aborted) setPending(null);
    },
    [],
  );

  const cancel = useCallback(() => {
    controller.current?.abort();
    setPending(null);
  }, []);

  return { pending, run, cancel };
}
