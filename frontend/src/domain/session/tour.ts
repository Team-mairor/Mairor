"use client";

import { useAuth } from "./auth";
import { useDevice } from "./device";
import { useSessionActions } from "./session-provider";

/** 화면 첫 진입 안내. 로그인 계정이고 화면이 준비됐으며 이번 로그인에서 그 화면 안내를 본 적 없을 때 show */
export function useTour(id: string, ready = true) {
  const { loggedIn } = useAuth();
  const { toured, markToured } = useDevice();
  const { storageLoaded, sessionChecked } = useSessionActions();
  return {
    show: ready && storageLoaded && sessionChecked && loggedIn && !toured.includes(id),
    done: () => markToured(id),
  };
}
