"use client";

import type { PouchItem } from "@/domain/pouch";

import { isMockPouchId, STORAGE_KEYS } from "./storage";
import { createStore } from "./store";

/** 저장값에서 예전 목업 파우치는 뺀다(옛 저장값 이전과 같은 기준을 매 로드에 적용) */
export function parsePouch(raw: unknown): PouchItem[] | undefined {
  return Array.isArray(raw)
    ? raw.filter((item: { id?: unknown }) => !isMockPouchId(item?.id))
    : undefined;
}

export const pouchStore = createStore<PouchItem[]>(
  "useMyPouch",
  STORAGE_KEYS.pouch,
  [],
  parsePouch,
);

/** 내 파우치 목록. 서버 응답이나 편집 결과를 setPouch로 넣는다 */
export function useMyPouch() {
  const { value, set } = pouchStore.useStore();
  return { pouch: value, setPouch: set };
}
