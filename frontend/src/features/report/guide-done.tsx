"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { completeExecution, useGuide, useRunQuery } from "@/features/guide";
import { useSession } from "@/features/session";

import { DoneView, PhotoSlot, type Save } from "./done-view";
import { guideReportSummary } from "./guide-report";

/** 실제 가이드 완료. 서버 실행을 완료하고 받은 recordId로 기기 리포트를 남긴다. 실패하면 같은 실행으로 다시 보낸다 */
export function GuideDone() {
  const router = useRouter();
  const query = useRunQuery();
  const { load } = useGuide();
  const { state, update } = useSession();
  const run = state.run;
  const guide = load.status === "ready" ? load.guide : null;
  const [save, setSave] = useState<Save>("saving");
  const [recordId, setRecordId] = useState<string | null>(null);
  // 응답이 올 때의 실행 상태로 저장 여부를 정한다
  const latest = useRef(run);
  useEffect(() => {
    latest.current = run;
  });

  /** 응답을 받았을 때도 같은 실행 · 같은 가이드 판이면 기기 리포트를 남긴다 */
  const commit = (reportId: string) => {
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

  // ?fail=1: 첫 저장을 실패로 보여 주는 확인용
  const failFirst = query?.get("fail") === "1";
  const persist = async (first: boolean) => {
    setSave("saving");
    const executionId = latest.current.executionId;
    if ((first && failFirst) || !executionId) return setSave("fail");
    try {
      const id = await completeExecution(executionId);
      if (!commit(id)) return setSave("fail");
      setRecordId(id);
      setSave("saved");
    } catch (e) {
      console.warn("완료 저장 실패", e);
      setSave("fail");
    }
  };
  const ready = !!query && !!guide;
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 진입 때 한 번 저장을 시작하고, 응답에 따라 상태를 바꾼다
    if (ready) void persist(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 진입 때 한 번만 저장한다
  }, [ready]);
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
      onRetry={() => void persist(false)}
      onHome={() => router.push("/home")}
      onReport={() => recordId && router.replace(`/my/report?id=${encodeURIComponent(recordId)}`)}
    />
  );
}
