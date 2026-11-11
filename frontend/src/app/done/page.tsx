"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useRunQuery as useQuery } from "@/features/guide";
import { DoneView, GuideDone, StepPhotoImg, useDoneSave } from "@/features/report";
import {
  keepStepPhotos,
  snapshotSteps,
  stepPhoto,
  useSession,
  type ReportSummary,
} from "@/features/session";
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
  // 촬영 기록이 아니라 실제로 남은 사진으로 판단한다. 최종 사진은 마지막 단계 사진
  const finalShot = stepPhoto(run.id, GUIDE_STEPS[n - 1].stepId);
  const hasPhoto = GUIDE_STEPS.some((s) => stepPhoto(run.id, s.stepId));
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
        ...(r.id && { runId: r.id }),
        videoId: video.id,
        items,
      };
      const rest = prev.reports.filter((x) => x.id !== id).map((r) => ({ ...r, isNew: false }));
      return { reports: [report, ...rest] };
    });
    if (run.id) keepStepPhotos(run.id);
    return true;
  };
  const { save, retry } = useDoneSave(!!query, query?.get("fail") === "1", commit);

  return (
    <DoneView
      total={n}
      title={picked.title}
      channel={picked.ch}
      hasFinal={!!finalShot}
      hasPhoto={hasPhoto}
      finalPhoto={finalShot && <StepPhotoImg photo={finalShot} alt="완성 사진" />}
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
