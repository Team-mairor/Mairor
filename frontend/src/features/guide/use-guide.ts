"use client";

import { createContext, useContext, useMemo } from "react";

import type { GuideLoad } from "./guide-store";
export type { GuideLoad } from "./guide-store";
export interface RunGuideValue {
  search: string | null;
  load: GuideLoad;
  retry: () => Promise<boolean>;
}
export const RunGuideContext = createContext<RunGuideValue | null>(null);

/** 루트 Provider의 공유 조회 결과 */
export function useGuide(): RunGuideValue {
  const value = useContext(RunGuideContext);
  if (!value) throw new Error("useGuide는 RunGuideProvider 안에서만 쓸 수 있습니다");
  return value;
}

/** 실행 경로의 쿼리. Navigation API가 없어도 동작한다 */
export function useRunQuery() {
  const { search } = useGuide();
  return useMemo(() => (search === null ? null : new URLSearchParams(search)), [search]);
}
