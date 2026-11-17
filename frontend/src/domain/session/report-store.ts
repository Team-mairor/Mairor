"use client";

import { isMockReportId, STORAGE_KEYS } from "./storage";
import { createStore } from "./store";
import type { ReportSummary } from "./types";

/** 저장값에서 예전 목업 리포트는 뺀다(옛 저장값 이전과 같은 기준을 매 로드에 적용) */
export function parseReports(raw: unknown): ReportSummary[] | undefined {
  return Array.isArray(raw)
    ? raw.filter((report: { id?: unknown }) => !isMockReportId(report?.id))
    : undefined;
}

export const reportStore = createStore<ReportSummary[]>(
  "useStoredReports",
  STORAGE_KEYS.reports,
  [],
  parseReports,
);

/** 이 기기에 저장한 리포트 목록. 서버 목록은 @/domain/report의 useReports다 */
export function useStoredReports() {
  const { value, set } = reportStore.useStore();
  return { reports: value, setReports: set };
}
