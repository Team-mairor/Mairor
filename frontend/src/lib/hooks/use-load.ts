"use client";

import { useEffect, useState } from "react";

import { isAbortError } from "@/lib/api";

export type Load<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; error: unknown };

/**
 * 화면에 보여 줄 데이터를 불러온다. key가 바뀔 때마다 다시 부르고, key가 바뀌거나 화면을 떠나면 이전 요청을 취소해
 * 늦은 응답이 새 결과를 덮지 않는다. key가 null이면 부르지 않는다(idle). run은 화면 밖(모듈)에 둔 함수를 넘긴다
 */
export function useLoad<T>(
  key: string | null,
  run: (key: string, signal: AbortSignal) => Promise<T>,
) {
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<Load<T>>({ status: key ? "loading" : "idle" });

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- key가 바뀔 때만 상태를 다시 정한다 */
    if (!key) {
      setLoad({ status: "idle" });
      return;
    }
    setLoad({ status: "loading" });
    /* eslint-enable react-hooks/set-state-in-effect */
    const controller = new AbortController();
    run(key, controller.signal).then(
      (data) => setLoad({ status: "ready", data }),
      (error: unknown) => {
        if (!isAbortError(error)) setLoad({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [key, run, attempt]);

  return { load, retry: () => setAttempt((n) => n + 1) };
}
