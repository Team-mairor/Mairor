"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FlowSteps } from "@/components/flow-steps";
import { useGuide } from "@/domain/guide-run";
import { emptyDraft, type ProductDraft } from "@/domain/pouch";
import {
  isGuideId,
  runHref,
  useMyPouch,
  usePendingGuide,
  useRun,
  useSessionActions,
} from "@/domain/session";
import { ProductSheet } from "@/features/pouch";
import { useHiddenVideo } from "@/vision/face";

import { jobReview, useAnalysisJob } from "./analysis-job";
import { AnalysisProgress } from "./analysis-progress";
import { FaceRegisterModal } from "./face-register-modal";
import { FoundProducts } from "./found-products";
import { pouchCategory } from "./loading-labels";
import { LoadingFooter, LoadingHeader, LoadingNoticeCard } from "./loading-parts";
import { describeLoading, jobFail, loadingCta, type Review } from "./loading-status";
import { PouchCheckModal } from "./pouch-check-modal";
import { ScanPreview } from "./scan-preview";
import { useAnalysisRetry } from "./use-analysis-retry";
import { useFaceFlow } from "./use-face-flow";

/** 04 로딩 · 준비. 분석 작업 또는 승인된 실제 가이드의 상태를 표시한다 */
export function LoadingScreen({ jobId }: { jobId: string | null }) {
  const router = useRouter();
  const { pouch } = useMyPouch();
  const { run, updateRun } = useRun();
  const { expireSession } = useSessionActions();
  const { setPendingGuide } = usePendingGuide();
  const { load } = useGuide();
  const activeJobId = jobId ?? run.jobId;
  const invalidEntry = !activeJobId && run.mode !== "guide";
  useEffect(() => {
    if (invalidEntry) router.replace("/select");
  }, [invalidEntry, router]);
  // 실제 작업에는 이전 실행의 '분석 없이 시작'이 섞이지 않게 한다
  const replay = !activeJobId && !!run.replay;
  // 상태 응답에 영상 정보가 없어, 이 작업으로 시작한 실행의 영상만 쓰고 모르면 비워 둔다
  const picked = activeJobId ? (run.jobId === activeJobId ? run.picked : null) : run.picked;
  const href = (path: string) => runHref(path, run.guideId);

  const [pouchModal, setPouchModal] = useState(false);
  const [newIds, setNewIds] = useState<string[]>([]);
  const [form, setForm] = useState<ProductDraft | null>(null);

  const live = useAnalysisJob(activeJobId);
  const job = activeJobId ? live.job : null;
  const pct = activeJobId ? live.pct : replay ? 100 : 0;
  const fail = activeJobId ? jobFail(live.error, job) : null;
  const review: Review = job ? jobReview(job) : null;
  // 분석이 끝나 공개되면 그 가이드로 바로 넘어간다. 옛 검수 대기 작업은 상태를 계속 받다가 승인되면 넘어간다
  const approvedGuide =
    job?.status === "COMPLETED" && job.reviewStatus === "APPROVED" && isGuideId(job.guideId)
      ? job.guideId
      : null;

  useEffect(() => {
    if (live.error?.code === "UNAUTHORIZED") {
      expireSession();
      router.replace("/login?expired=basic");
    }
  }, [live.error, expireSession, router]);

  // 카메라 영상은 등록 모달 안에서만 보여 준다.
  useHiddenVideo();

  const retry = useAnalysisRetry({ activeJobId, restart: live.restart });
  const face = useFaceFlow({
    replay,
    activeJobId,
    job,
    pct,
    fail,
    review,
    openPouch: () => setPouchModal(true),
  });
  const guideMode = run.mode === "guide";
  const status = describeLoading({
    pct,
    job,
    activeJobId,
    replay,
    fail,
    review,
    approvedGuide,
    retryRefused: retry.refused,
    hasPicked: !!picked,
    guideMode,
    guideReady: load.status === "ready",
  });
  const { notice, guideOk } = status;
  const cta = loadingCta({
    approvedGuide,
    review,
    guideOk,
    faceCaptured: face.captured,
    faceOk: face.ok,
    guideMode,
    savingFace: face.saving,
    faceSaveError: face.saveError,
  });

  const barText = replay
    ? run.replay === "guide"
      ? "분석해 둔 가이드가 있어 바로 시작해요"
      : "이전에 분석한 가이드를 그대로 써요"
    : status.done
      ? "영상 분석이 끝났어요"
      : "영상 분석은 그대로 진행 중이에요";

  const actions = {
    guide: () =>
      // 실행 전환은 주소 변경 뒤 Provider가 처리한다.
      router.push(
        runHref("/loading", approvedGuide!, activeJobId ? { jobId: activeJobId } : undefined),
      ),
    home: () => {
      if (picked) setPendingGuide({ title: picked.title, ytid: picked.ytid, status: "pending" });
      router.push("/home");
    },
    select: () => router.push("/select"),
    face: face.open,
    "save-face": () => void face.savePrepared(),
    check: () => router.push(href("/check")),
  };

  const closePouch = () => {
    setPouchModal(false);
    updateRun({ pouchReviewed: true }, run.id);
    if (replay && face.ok) router.push(href("/check"));
  };

  if (invalidEntry)
    return (
      <main className="flex flex-1 items-center justify-center px-8 text-center text-[18px] text-mute">
        분석 또는 가이드 정보가 없어요. 영상을 다시 골라 주세요.
      </main>
    );

  return (
    <main className="relative flex min-h-(--screen-h) flex-1 flex-col bg-white text-ink">
      <LoadingHeader
        replay={replay}
        replayKind={run.replay}
        onBack={() => router.push("/select")}
      />

      <div className="flex min-h-0 flex-1 flex-col justify-between gap-6 overflow-hidden px-10 pt-7 pb-8">
        <FlowSteps step={1} ready={replay} />

        <ScanPreview
          ytid={picked?.ytid ?? null}
          title={picked?.title ?? "분석 중인 영상"}
          status={status.scanStatus}
          running={!!activeJobId && !fail && pct < 100}
          pct={pct}
          rows={status.rows}
          foundCount={status.foundCount}
        />

        <AnalysisProgress
          pct={pct}
          phaseIdx={status.phaseIdx}
          phaseEn={status.phaseEn}
          phaseLabel={status.phaseLabel}
          eta={status.eta}
          failed={!!fail}
        />

        {notice ? (
          <LoadingNoticeCard notice={notice} retryError={fail === "stopped" ? retry.error : null} />
        ) : guideMode && load.status === "ready" ? (
          <div className="rounded-3xl bg-cream px-7 py-6 text-[20px] text-ink">
            가이드 · {load.guide.steps.length}단계가 준비됐어요.
          </div>
        ) : (
          <FoundProducts
            rows={status.rows}
            foundCount={status.foundCount}
            haveCount={status.haveCount}
            onAdd={(row) =>
              setForm(
                emptyDraft({
                  cat: pouchCategory(row?.cat),
                  name: row?.name ?? "",
                  custom: Boolean(row?.name),
                }),
              )
            }
          />
        )}
      </div>

      <LoadingFooter
        readyItems={[
          ["가이드 준비", status.guideState, guideOk],
          [
            "얼굴 인식 준비",
            face.ok ? "완료" : face.captured ? "촬영 완료" : face.modal ? "등록 중" : "등록 필요",
            face.ok,
          ],
        ]}
        saveError={face.saveError}
        onPouch={activeJobId && !fail && !review ? () => setPouchModal(true) : null}
        failed={
          fail
            ? {
                canRetry: !!notice?.retry,
                retrying: retry.retrying,
                onRetry: () => void retry.retry(),
              }
            : null
        }
        cta={{
          label: cta.label,
          disabled: (!approvedGuide && !review && !guideOk) || face.saving,
          onClick: () => cta.action && actions[cta.action](),
        }}
        onSelect={actions.select}
      />

      {face.modal && (
        <FaceRegisterModal
          pct={pct}
          replay={replay}
          pouchReviewed={run.pouchReviewed}
          barText={barText}
          runId={run.id}
          onLater={face.later}
          onDone={face.register}
        />
      )}

      <PouchCheckModal
        open={pouchModal}
        pct={pct}
        barText={barText}
        pouch={pouch}
        changed={newIds.length > 0}
        onClose={closePouch}
        onEdit={(p) => setForm({ ...p })}
        onAdd={() => setForm(emptyDraft())}
      />

      {form && (
        <ProductSheet
          draft={form}
          onClose={() => setForm(null)}
          onSaved={(item, isNew) => isNew && setNewIds((ids) => [item.id, ...ids])}
        />
      )}
    </main>
  );
}
