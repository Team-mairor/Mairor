"use client";

import { STORAGE_KEYS, isObject } from "./storage";
import { createStore } from "./store";

/** 검수 완료 카드에는 실행에 사용할 guideId가 있어야 한다. */
export type PendingGuide = { title: string; ytid: string | null } & (
  { status: "pending"; guideId?: null } | { status: "approved"; guideId: string }
);

function parsePending(raw: unknown): PendingGuide | null | undefined {
  if (raw === null) return null;
  return isObject(raw) ? (raw as PendingGuide) : undefined;
}

export const pendingGuideStore = createStore<PendingGuide | null>(
  "usePendingGuide",
  STORAGE_KEYS.pendingGuide,
  null,
  parsePending,
);

/** 영상 검수를 기다리는 가이드 카드 */
export function usePendingGuide() {
  const { value, set } = pendingGuideStore.useStore();
  return { pendingGuide: value, setPendingGuide: set };
}
