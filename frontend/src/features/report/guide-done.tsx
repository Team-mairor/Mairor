"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { useGuide, useRunQuery } from "@/features/guide";
import { useSession } from "@/features/session";

import { DoneView, PhotoSlot, useDoneSave } from "./done-view";
import { guideReportSummary } from "./guide-report";

/** 실제 가이드 완료. 같은 실행의 가이드 단계로 스냅샷을 남긴다 */
export function GuideDone() {
  const router = useRouter();
  const query = useRunQuery();
  const { load } = useGuide();
  const { state, update } = useSession();
  const run = state.run;
  const guide = load.status === "ready" ? load.guide : null;
  const reportId = `rp-${run.id}`;
  // 타이머가 끝날 때의 실행 상태로 저장 여부를 정한다
  const latest = useRef(run);
  useEffect(() => {
    latest.current = run;
  });

  const commit = () => {
    const r = latest.current;
    if (!guide || r.id !== run.id || r.mode !== "guide" || r.guideVersion !== guide.guideVersion)
      return false;
    update((prev) => {
      const r = prev.run;
      if (r.id !== run.id || r.mode !== "guide" || r.guideVersion !== guide.guideVersion) return {};
      const report = guideReportSummary(reportId, new Date(), guide, r, prev.pouch);
      const rest = prev.reports
        .filter((x) => x.id !== reportId)
        .map((x) => ({ ...x, isNew: false }));
      return { reports: [report, ...rest] };
    });
    return true;
  };
  const { save, retry } = useDoneSave(!!query && !!guide, query?.get("fail") === "1", commit);
  if (!guide) return null;

  const last = guide.steps.at(-1)?.stepId;
  const hasPhoto = run.photoOk && run.captures.length > 0;
  const hasFinal = run.photoOk && !!last && run.captures.includes(last);

  // 이동만 한다. 실행은 실행 화면을 벗어날 때 끝난다
  return (
    <DoneView
      total={guide.steps.length}
      title={guide.title}
      channel={guide.channelTitle}
      hasFinal={hasFinal}
      hasPhoto={hasPhoto}
      finalPhoto={<PhotoSlot label="마지막 단계 사진을 남겼어요" />}
      save={save}
      onRetry={retry}
      onHome={() => router.push("/home")}
      onReport={() => router.replace(`/my/report?id=${reportId}`)}
    />
  );
}
