"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import {
  COMPAT_TYPES,
  checkRows,
  isCompatible,
  pickCounts,
  swapList,
  userChoice,
  useGuideMatch,
  withChoice,
  type StepMatch,
} from "@/domain/check";
import { useGuide } from "@/domain/guide-run";
import { emptyDraft, type PouchItem, type ProductDraft } from "@/domain/pouch";
import {
  runHref,
  type Choice,
  type MatchKind,
  useAuth,
  useMyPouch,
  usePouchSync,
  useRun,
} from "@/domain/session";
import { GlassPanel, LiveNote, LiveTag, RoundBack, useLiveState } from "@/features/live";
import { ProductSheet } from "@/features/pouch";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { useHiddenVideo } from "@/vision/face";

import { CheckHeader } from "./check-header";
import { CheckStepRow, groupLabel, productText } from "./check-step-row";
import { GroupTabs } from "./group-tabs";
import { PouchModal } from "./pouch-modal";
import { StartModal } from "./start-modal";
import { SwapPanel } from "./swap-panel";
import { Toast } from "./toast";
import { useStartExecution } from "./use-start-execution";

const NO_MATCHES = new Map<string, StepMatch>();

/** 실제 가이드의 제품 체크. 서버 매칭으로 보유·대체·없음을 나누고, 사용자가 바꾼 것은 선택으로 남긴다 */
export function GuideCheck() {
  const router = useRouter();
  const { loggedIn } = useAuth();
  const { pouch: stored } = useMyPouch();
  const { run, updateRun } = useRun();
  const { load } = useGuide();
  const pouchSync = usePouchSync();
  const pouchReady = !loggedIn || pouchSync.status === "ready";
  const pouch = pouchReady ? stored : [];

  const [group, setGroup] = useState<MatchKind | null>(null);
  const [swapFor, setSwapFor] = useState<string | null>(null);
  const [pouchModal, setPouchModal] = useState(false);
  const [form, setForm] = useState<ProductDraft | null>(null);
  const [startAsk, setStartAsk] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const toastT = useTimeout();
  const { note, reason } = useLiveState();
  useHiddenVideo();
  // 제품을 등록·수정·삭제하면 다시 맞춘다. 수정은 ID가 그대로라 항목 값 전체를 기준으로 본다
  const { load: matching, retry } = useGuideMatch(
    pouchReady ? run.guideId : null,
    JSON.stringify(pouch),
  );

  const guide = load.status === "ready" ? load.guide : null;
  const rows = !guide
    ? []
    : matching.status === "ready"
      ? checkRows(guide.steps, run.choice, pouch, matching.byStep)
      : checkRows(
          guide.steps,
          run.choice,
          pouch,
          NO_MATCHES,
          matching.status === "loading" ? "pending" : "failed",
        );
  const starter = useStartExecution({
    guide,
    rows,
    matching,
    retry,
    onFinish: () => setStartAsk(false),
  });

  if (!guide) return null;
  if (loggedIn && pouchSync.status === "error")
    return (
      <main className="flex flex-1 items-center justify-center px-8 text-center text-white">
        <div className="flex flex-col items-center gap-4">
          <p>내 파우치를 불러오지 못했어요. 다시 불러온 뒤 제품을 맞춰 볼게요.</p>
          <button type="button" onClick={pouchSync.retry} className="font-bold underline">
            파우치 다시 불러오기
          </button>
        </div>
      </main>
    );
  if (loggedIn && !pouchReady)
    return (
      <main className="flex flex-1 items-center justify-center px-8 text-center text-white">
        내 파우치를 불러오고 있어요.
      </main>
    );
  const counts = pickCounts(rows);
  const active = group ?? (counts.none ? "none" : counts.sub ? "sub" : "same");
  const shown = rows.filter((r) => r.pick.kind === active);
  const swapRow = rows.find((r) => r.step.stepId === swapFor) ?? null;
  const swapMatch =
    swapRow && matching.status === "ready" ? matching.byStep.get(swapRow.step.stepId) : undefined;

  const setChoice = (stepId: string, value: Choice | null) =>
    updateRun((prev) => ({ choice: withChoice(prev.choice, stepId, value) }), run.id);
  const closeSwap = () => setSwapFor(null);
  const showToast = (ok: boolean, text: string) => {
    setToast({ ok, text });
    toastT.set(() => setToast(null), 2800);
  };
  // 등록·수정하면 파우치가 바뀌어 다시 맞춘다
  const onSaved = (item: PouchItem, isNew: boolean) => {
    const done = isNew ? "등록 완료" : "수정 완료";
    if (isNew && swapRow && isCompatible(swapRow.step, item))
      showToast(true, `'${item.name}' ${done} · 목록에서 고를 수 있어요`);
    else showToast(true, `'${item.name}' ${done} · 다시 맞춰 볼게요`);
  };

  return (
    <main className="relative flex flex-1 flex-col">
      <div className="absolute inset-x-5 top-5 flex items-center justify-between gap-3">
        <LiveTag />
      </div>

      <GlassPanel
        className="inset-x-0 top-[84px] bottom-0 gap-[22px] rounded-t-[36px] rounded-b-none border-x-0 border-b-0 px-0 pt-[30px] pb-5"
        coversFace={false}
      >
        {swapRow && (
          <SwapPanel
            title={`${swapRow.step.label} 제품 고르기`}
            refProduct={{
              name: productText(swapRow.step) ?? "영상 속 제품 정보 없음",
              color: null,
            }}
            list={swapList(swapRow, pouch, swapMatch)}
            curId={swapRow.pick.kind === "none" ? null : swapRow.pick.item.id}
            skipped={swapRow.pick.kind === "none" && swapRow.pick.reason === "skipped"}
            ranked
            emptyText={
              matching.status !== "ready"
                ? "파우치 제품 매칭을 불러온 뒤 교체 후보를 보여드릴게요"
                : COMPAT_TYPES[swapRow.step.makeup].length
                  ? `파우치에 ${COMPAT_TYPES[swapRow.step.makeup].join("·")} 종류 제품이 없어요`
                  : "이 단계에 맞춰 볼 제품 종류가 아직 정해지지 않았어요"
            }
            onPick={(choice) => {
              setChoice(swapRow.step.stepId, choice);
              closeSwap();
            }}
            // 직접 고른 것을 지우면 서버 매칭으로 돌아간다
            onClear={
              !userChoice(run.choice, swapRow.step.stepId)
                ? undefined
                : () => {
                    setChoice(swapRow.step.stepId, null);
                    closeSwap();
                  }
            }
            onClose={closeSwap}
          />
        )}
        {toast && <Toast toast={toast} />}
        <CheckHeader
          matched={counts.same + counts.sub}
          total={rows.length}
          matching={matching}
          pouchEmpty={!pouch.length}
          onRetry={retry}
          onRegister={() => setPouchModal(true)}
        />

        <GroupTabs active={active} counts={counts} onChange={setGroup} />

        <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto overscroll-contain px-8">
          {shown.length === 0 ? (
            <div className="py-10 text-center text-[20px] font-semibold text-ash">
              {groupLabel(active)} 단계가 없어요
            </div>
          ) : (
            shown.map((row) => (
              <CheckStepRow
                key={row.step.stepId}
                row={row}
                onSwap={() => setSwapFor(row.step.stepId)}
              />
            ))
          )}
        </div>

        {reason === "error" && (
          <LiveNote note={note} className="relative inset-x-auto top-auto mx-8 shrink-0" />
        )}
        <div className="flex shrink-0 items-center gap-2.5 px-8">
          <RoundBack
            onClick={() => router.push(runHref("/loading", run.guideId))}
            label="준비 화면으로"
          />
          <PillButton
            size="cta"
            trailing
            onClick={() => setStartAsk(true)}
            // 맞춰 보지 못한 단계를 생략으로 저장하지 않도록, 매칭 결과가 있을 때만 시작한다
            disabled={matching.status !== "ready"}
            className="min-w-0 flex-1"
          >
            이 조합으로 시작
          </PillButton>
        </div>
      </GlassPanel>

      <PouchModal
        open={pouchModal}
        pouch={pouch}
        onEdit={(p) => setForm({ ...p })}
        onAdd={() => setForm(emptyDraft())}
        onClose={() => setPouchModal(false)}
      />

      {/* 시작하면 직접 고르지 않은 단계에 화면에 보이는 결과를 자동 선택으로 저장한다. 없음은 생략 */}
      <StartModal
        open={startAsk}
        counts={counts}
        missing={rows
          .filter((r) => r.pick.kind === "none")
          .map((r) => ({
            key: r.step.stepId,
            label: `${r.step.label} · ${productText(r.step) ?? "제품 정보 없음"}`,
            color: null,
          }))}
        onRecheck={() => {
          setStartAsk(false);
          setGroup("none");
        }}
        busy={starter.starting}
        error={starter.error}
        onStart={() => void starter.start()}
        onClose={() => {
          setStartAsk(false);
          starter.clearError();
        }}
      />

      {form && <ProductSheet draft={form} onClose={() => setForm(null)} onSaved={onSaved} />}
    </main>
  );
}
