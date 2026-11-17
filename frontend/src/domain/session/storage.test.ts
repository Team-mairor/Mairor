// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";

import { LEGACY_STORAGE_KEY, migrateLegacySession, STORAGE_KEYS } from "./storage";

const get = (key: string) => JSON.parse(localStorage.getItem(key) ?? "null");

describe("옛 세션 저장값 이전", () => {
  beforeEach(() => localStorage.clear());

  it("옛 키 하나를 상태별 키로 나누고 옛 키를 지운다", () => {
    localStorage.setItem(
      LEGACY_STORAGE_KEY,
      JSON.stringify({
        loggedIn: true,
        email: "a@b.c",
        nickname: "닉",
        sessionExpired: false,
        onboarded: true,
        tutSeen: false,
        pouch: [{ id: "x1" }],
        reports: [{ id: "r1" }],
        pendingGuide: { title: "t", ytid: null, status: "pending" },
        run: { id: "old" },
      }),
    );
    migrateLegacySession();
    expect(localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull();
    expect(get(STORAGE_KEYS.auth)).toEqual({
      loggedIn: true,
      email: "a@b.c",
      nickname: "닉",
      sessionExpired: false,
    });
    expect(get(STORAGE_KEYS.device)).toEqual({ onboarded: true, tutSeen: false });
    expect(get(STORAGE_KEYS.pouch)).toEqual([{ id: "x1" }]);
    expect(get(STORAGE_KEYS.reports)).toEqual([{ id: "r1" }]);
    expect(get(STORAGE_KEYS.pendingGuide)).toMatchObject({ title: "t" });
    expect(Object.keys(localStorage).join()).not.toMatch(/run/i);
  });

  it("예전 목업 파우치·리포트는 옮기지 않는다", () => {
    localStorage.setItem(
      LEGACY_STORAGE_KEY,
      JSON.stringify({
        pouch: [{ id: "p1" }, { id: "real" }],
        reports: [{ id: "rp2" }, { id: "x" }],
      }),
    );
    migrateLegacySession();
    expect(get(STORAGE_KEYS.pouch)).toEqual([{ id: "real" }]);
    expect(get(STORAGE_KEYS.reports)).toEqual([{ id: "x" }]);
  });

  it("새 키가 이미 있으면 덮어쓰지 않는다", () => {
    localStorage.setItem(STORAGE_KEYS.pouch, JSON.stringify([{ id: "new" }]));
    localStorage.setItem(LEGACY_STORAGE_KEY, JSON.stringify({ pouch: [{ id: "old" }] }));
    migrateLegacySession();
    expect(get(STORAGE_KEYS.pouch)).toEqual([{ id: "new" }]);
    expect(localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull();
  });

  it("깨진 옛 값이나 옛 값이 없을 때는 아무것도 만들지 않는다", () => {
    migrateLegacySession();
    expect(localStorage.length).toBe(0);
    localStorage.setItem(LEGACY_STORAGE_KEY, "{깨짐");
    migrateLegacySession();
    expect(Object.keys(localStorage)).toEqual([LEGACY_STORAGE_KEY]);
  });
});
