"use client";

import { categoryOfPart, MAKEUP_LABEL } from "@/domain/guide";
import type { GuideReportStep, ReportSummary } from "@/domain/session";
import { api, type Page, type ReportRecordDto, type ReportSummaryDto } from "@/lib/api";
import { useLoad } from "@/lib/hooks/use-load";

const RECORDS = "/v1/users/me/history-records";

/** 한 번에 받는 리포트 수. 넘기기 없이 이만큼만 보여 준다 */
export const REPORT_PAGE_SIZE = 50;

/** GET /v1/users/me/history-records. 완료 시각 최신순 */
function fetchReports(_account: string, signal: AbortSignal) {
  return api.get<Page<ReportSummaryDto>>(RECORDS, { query: { size: REPORT_PAGE_SIZE }, signal });
}

/** GET …/{recordId} */
function fetchReport(recordId: string, signal: AbortSignal) {
  return api.get<ReportRecordDto>(`${RECORDS}/${encodeURIComponent(recordId)}`, { signal });
}

/** DELETE …/{recordId}. 사진을 일부 못 지우면 503이고, 다시 요청하면 남은 것을 지운다 */
export function deleteReport(recordId: string) {
  return api.delete(`${RECORDS}/${encodeURIComponent(recordId)}`);
}

/** account(로그인한 계정)가 바뀌면 다시 받고, null이면 부르지 않는다 */
export const useReports = (account: string | null) => useLoad(account, fetchReports);

export const useReport = (account: string | null, recordId: string | null) =>
  useLoad(account && recordId ? recordId : null, fetchReport);

/** 화면의 날짜 표기(기기 리포트와 같다) */
function dateText(iso: string) {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

const partLabel = (part: string) =>
  part in MAKEUP_LABEL ? MAKEUP_LABEL[part as keyof typeof MAKEUP_LABEL] : MAKEUP_LABEL.other;

/** 목록 한 줄 → 화면의 리포트 */
export function fromSummary(d: ReportSummaryDto): ReportSummary {
  return {
    id: d.recordId,
    guideId: d.guideId,
    title: d.videoTitle,
    date: dateText(d.completedAt),
    steps: d.stepCount,
    subs: d.substituteCount,
    finalPhoto: d.completedPhoto !== null,
    photoUrl: d.completedPhoto?.url ?? null,
    videoId: d.videoId,
  };
}

/** 상세 스냅샷 → 화면의 리포트. 고른 제품이 없으면 생략이다(서버 기록에는 "기록 없음"이 없다) */
export function fromRecord(d: ReportRecordDto): ReportSummary {
  const steps: GuideReportStep[] = d.steps.map((s) => {
    const ref = s.referenceProduct;
    return {
      stepId: s.stepId,
      title: s.partLabel ?? partLabel(s.part),
      category: categoryOfPart(s.part),
      summary: s.summary ?? s.actions[0]?.text ?? null,
      ref: ref && (ref.name || ref.shadeName) ? { name: ref.name, shade: ref.shadeName } : null,
      pick: s.selectedProduct && !s.skipped ? "picked" : "skipped",
      used: s.selectedProduct
        ? {
            brand: s.selectedProduct.brand,
            name: s.selectedProduct.name,
            shade: s.selectedProduct.shadeName,
          }
        : null,
      photo: s.photo !== null,
      photoUrl: s.photo?.url ?? null,
    };
  });
  return {
    id: d.recordId,
    guideId: d.guideId,
    guideVersion: d.guideVersion,
    title: d.videoTitle,
    date: dateText(d.completedAt),
    steps: d.stepCount,
    subs: d.substituteCount,
    finalPhoto: d.completedPhoto !== null,
    photoUrl: d.completedPhoto?.url ?? null,
    videoId: d.videoId,
    guide: {
      videoId: d.videoId,
      youtubeVideoId: null,
      channelTitle: d.channelTitle,
      steps,
    },
  };
}
