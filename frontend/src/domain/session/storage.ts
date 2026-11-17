"use client";

import { useEffect, useState } from "react";

/** 상태마다 키를 따로 둔다. 실행(run)은 메모리에만 두어 키가 없다 */
export const STORAGE_KEYS = {
  auth: "mairor-auth-v1",
  device: "mairor-device-v1",
  pouch: "mairor-pouch-v1",
  reports: "mairor-reports-v1",
  pendingGuide: "mairor-pending-guide-v1",
} as const;

/** 상태를 하나로 저장하던 옛 키. 첫 로드 때 상태별 키로 옮기고 지운다 */
export const LEGACY_STORAGE_KEY = "mairor-session-v2";

function read(key: string): unknown {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 저장 실패는 화면에 영향 없음
  }
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);

/** 예전 목업이 만든 파우치(p1…)·리포트(rp1~rp4) id. 저장된 목록에서는 버린다 */
export const isMockPouchId = (id: unknown) => /^p\d+$/.test(String(id ?? ""));
export const isMockReportId = (id: unknown) => /^rp[1-4]$/.test(String(id ?? ""));

/**
 * 옛 저장값을 상태별 키로 나눈다. 새 키가 이미 있으면 덮어쓰지 않는다.
 * 예전 목업 파우치(p1…)·리포트(rp1~rp4)는 옮기지 않는다
 */
export function migrateLegacySession() {
  const saved = read(LEGACY_STORAGE_KEY);
  if (saved === undefined) return;
  try {
    if (isObject(saved)) {
      const put = (key: string, value: unknown) => {
        if (value !== undefined && localStorage.getItem(key) === null) write(key, value);
      };
      put(STORAGE_KEYS.auth, {
        loggedIn: saved.loggedIn === true,
        email: typeof saved.email === "string" ? saved.email : "",
        nickname: typeof saved.nickname === "string" ? saved.nickname : "",
        sessionExpired: saved.sessionExpired === true,
      });
      put(STORAGE_KEYS.device, {
        onboarded: saved.onboarded === true,
        tutSeen: saved.tutSeen === true,
      });
      if (Array.isArray(saved.pouch))
        put(
          STORAGE_KEYS.pouch,
          saved.pouch.filter((item: { id?: unknown }) => !isMockPouchId(item?.id)),
        );
      if (Array.isArray(saved.reports))
        put(
          STORAGE_KEYS.reports,
          saved.reports.filter((report: { id?: unknown }) => !isMockReportId(report?.id)),
        );
      if (saved.pendingGuide !== undefined) put(STORAGE_KEYS.pendingGuide, saved.pendingGuide);
    }
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // 저장소를 못 쓰면 기본값으로 시작한다
  }
}

/**
 * localStorage와 맞춘 상태. 브라우저에서만 읽을 수 있어 마운트 뒤에 저장값을 넣고,
 * loaded가 true가 된 다음 렌더부터 저장한다(기본값으로 저장값을 덮어쓰지 않게)
 */
export function usePersistedState<T>(
  key: string,
  initial: T,
  parse: (raw: unknown) => T | undefined,
) {
  const [value, setValue] = useState<T>(initial);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    migrateLegacySession();
    const saved = parse(read(key));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 저장소는 브라우저에서만 읽을 수 있다
    if (saved !== undefined) setValue(saved);
    setLoaded(true);
    // parse는 모듈 상수라 바뀌지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (loaded) write(key, value);
  }, [loaded, key, value]);

  return [value, setValue, loaded] as const;
}

export { isObject };
