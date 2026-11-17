"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { fetchAllPouch, fromApi, writeCount } from "@/domain/pouch/pouch-api";
import { awaitsCatalog, samePouch } from "@/domain/pouch/pouch-refresh";
import { ApiError, isAbortError } from "@/lib/api";

import { useAuth } from "./auth";
import { useMyPouch } from "./pouch-store";
import { useSessionActions } from "./session-provider";

export type PouchSync = "idle" | "loading" | "ready" | "error";

/** 카탈로그에 연결되지 않은 항목이 있을 때 목록을 다시 받는 간격과 지속 시간. 수집은 보통 몇 분 안에 끝난다 */
const REFRESH_EVERY_MS = 15_000;
const REFRESH_WINDOW_MS = 5 * 60_000;

/** 로그인했으면 서버 파우치로 세션 파우치(pouch)를 바꾼다. 계정이 바뀌면 다시 받는다 */
export function usePouchSync() {
  const { loggedIn, email } = useAuth();
  const { pouch, setPouch } = useMyPouch();
  const { sessionChecked, expireSession } = useSessionActions();
  const router = useRouter();
  const account = sessionChecked && loggedIn ? email : null;
  const on = account !== null;
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<PouchSync>("idle");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!on) return;
    /* eslint-disable react-hooks/set-state-in-effect -- 로그인 상태가 바뀔 때만 다시 받는다 */
    setStatus("loading");
    setError(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    const controller = new AbortController();
    const seen = writeCount();
    fetchAllPouch(controller.signal).then(
      (items) => {
        if (writeCount() !== seen) return setAttempt((n) => n + 1);
        setPouch(items.map(fromApi));
        setStatus("ready");
      },
      (e: unknown) => {
        if (isAbortError(e)) return;
        if (e instanceof ApiError && e.code === "UNAUTHORIZED") {
          expireSession();
          router.replace("/login?expired=basic");
          return;
        }
        setError(e);
        setStatus("error");
      },
    );
    return () => {
      controller.abort();
      setStatus("idle");
    };
  }, [on, account, attempt, setPouch, expireSession, router]);

  // 수집이 끝나 카탈로그 색이 채워지면 보이는 색이 바뀐다(S15P31A306-531). 화면을 다시 보게 되면(탭 복귀·포커스) 받고,
  // 카탈로그에 연결되지 않은 항목이 있는 동안은 일정 시간 주기적으로 조용히 다시 받는다(로딩 표시 없이, 바뀐 것만 반영)
  const pouchRef = useRef(pouch);
  useEffect(() => {
    pouchRef.current = pouch;
  });
  const waiting = on && awaitsCatalog(pouch);
  useEffect(() => {
    if (!on) return;
    let controller: AbortController | null = null;
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      controller?.abort();
      const own = new AbortController();
      controller = own;
      const seen = writeCount();
      fetchAllPouch(own.signal).then(
        (items) => {
          if (writeCount() !== seen) return;
          const next = items.map(fromApi);
          if (!samePouch(pouchRef.current, next)) setPouch(next);
        },
        () => {},
      );
    };
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("focus", refresh);
    const stopAt = Date.now() + REFRESH_WINDOW_MS;
    let timer: ReturnType<typeof setInterval> | undefined;
    if (waiting) {
      timer = setInterval(() => {
        if (Date.now() >= stopAt) clearInterval(timer);
        else refresh();
      }, REFRESH_EVERY_MS);
    }
    return () => {
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("focus", refresh);
      clearInterval(timer);
      controller?.abort();
    };
  }, [on, account, waiting, setPouch]);

  // effect가 돌기 전 첫 렌더도 loading으로 알려 지난 파우치가 보이지 않게 한다
  const shown: PouchSync = !on ? "idle" : status === "idle" ? "loading" : status;
  return { status: shown, error, retry: () => setAttempt((n) => n + 1) };
}
