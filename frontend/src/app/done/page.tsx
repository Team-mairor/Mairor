"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useRunQuery as useQuery } from "@/features/guide";
import { DoneView, GuideDone, useDoneSave } from "@/features/report";
import { snapshotSteps, useSession, type ReportSummary } from "@/features/session";
import { GUIDE_STEPS, VIDEOS, REF_PRODUCTS } from "@/mocks/mock-data";

/**
 * 11 완성. 기록 저장 → 리포트 보기.
 * ?fail=1 은 저장 실패 상태 확인용.
 */
export default function DonePage() {
  const { state } = useSession();
  return state.run.mode === "guide" ? <GuideDone /> : <SampleDone />;
}

/** 샘플 기록은 단계 번호로 사진을 남긴다 */
const sampleCaptures = (captures: string[]) =>
  GUIDE_STEPS.flatMap((s, i) => (captures.includes(s.stepId) ? [i] : []));

function SampleDone() {
  const router = useRouter();
  const query = useQuery();
  const { state, update, endRun } = useSession();
  const run = state.run;
  const picked = run.picked ?? VIDEOS[0];
  const n = GUIDE_STEPS.length;
  const captures = sampleCaptures(run.captures);
  // 최종 사진은 마지막 단계를 찍었을 때만. 중간 단계 사진은 따로 센다
  const hasFinal = run.photoOk && captures.includes(n - 1);
  const hasPhoto = run.photoOk && captures.length > 0;
  // 기록 id = 실행 id. 다시 시도해도 같은 기록을 덮어써 중복이 생기지 않는다.
  // 실행 id가 없는 예전 세션은 화면에 머무는 동안 한 번 만든 id를 쓴다
  const [fallbackId] = useState(() => `rp${Date.now()}`);
  const reportId = run.id ? `rp-${run.id}` : fallbackId;

  // 저장 성공 시점에 기록을 만든다 (upsert). 타이머가 끝날 때의 최신 실행 상태(prev.run)로 기록한다
  const latest = useRef(run);
  useEffect(() => {
    latest.current = run;
  });
  const commit = () => {
    const now = latest.current;
    if (now.id !== run.id || now.mode === "guide") return false;
    const d = new Date();
    update((prev) => {
      const r = prev.run;
      if (r.id !== run.id || r.mode === "guide") return {};
      const id = r.id ? `rp-${r.id}` : fallbackId;
      const video = r.picked ?? VIDEOS[0];
      const items = snapshotSteps(REF_PRODUCTS, r, prev.pouch);
      const shots = r.photoOk ? sampleCaptures(r.captures) : [];
      const report: ReportSummary = {
        id,
        title: video.title,
        date: `${d.getMonth() + 1}월 ${d.getDate()}일`,
        steps: n,
        subs: items.filter((s) => s.kind === "sub").length,
        isNew: true,
        noPhoto: !r.photoOk,
        finalPhoto: shots.includes(n - 1),
        captures: shots,
        videoId: video.id,
        items,
      };
      const rest = prev.reports.filter((x) => x.id !== id).map((r) => ({ ...r, isNew: false }));
      return { reports: [report, ...rest] };
    });
    return true;
  };
  const { save, retry } = useDoneSave(!!query, query?.get("fail") === "1", commit);

  return (
    <DoneView
      total={n}
      title={picked.title}
      channel={picked.ch}
      hasFinal={hasFinal}
      hasPhoto={hasPhoto}
      finalPhoto={
        // eslint-disable-next-line @next/next/no-img-element -- 샘플
        <img
          src="/images/sample-face.png"
          alt="완성 사진"
          className="absolute top-0 left-0 h-auto w-[187.9%] max-w-none"
          style={{ marginTop: "-92.7%" }}
        />
      }
      save={save}
      onRetry={retry}
      onHome={() => {
        endRun(run.id);
        router.push("/home");
      }}
      onReport={() => {
        endRun(run.id);
        router.replace(`/my/report?id=${reportId}`);
      }}
    />
  );
}
