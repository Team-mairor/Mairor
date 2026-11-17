import { describe, expect, it } from "vitest";

import { POUCH_OPEN_COOLDOWN_MS, shouldPlayPouchOpenFx } from "./pouch-open-policy";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
}

describe("파우치 진입 연출", () => {
  it("처음 들어오면 재생하고 5분 안에 다시 들어오면 생략한다", () => {
    const storage = memoryStorage();
    const now = 1_000_000;

    expect(shouldPlayPouchOpenFx(storage, now)).toBe(true);
    expect(shouldPlayPouchOpenFx(storage, now + POUCH_OPEN_COOLDOWN_MS - 1)).toBe(false);
  });

  it("마지막 재생 후 5분이 지나면 다시 재생한다", () => {
    const storage = memoryStorage();
    const now = 1_000_000;

    shouldPlayPouchOpenFx(storage, now);

    expect(shouldPlayPouchOpenFx(storage, now + POUCH_OPEN_COOLDOWN_MS)).toBe(true);
  });
});
