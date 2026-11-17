"use client";

import { useRunQuery } from "@/domain/guide-run";
import { LoadingScreen } from "@/features/loading";

/** 04 로딩 · 준비. 분석 작업 또는 승인된 실제 가이드의 상태를 표시한다 */
export default function LoadingPage() {
  const query = useRunQuery();
  // 주소를 읽은 뒤 그린다. jobId가 바뀌면 이전 작업의 진행률·모달 상태를 버리고 새로 시작한다
  if (!query) return null;
  const jobId = query.get("jobId");
  return <LoadingScreen key={jobId ?? ""} jobId={jobId} />;
}
