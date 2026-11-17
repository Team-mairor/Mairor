"use client";

import { Check, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { facePhoto, useHiddenVideo } from "@/features/face";
import {
  ExecutionMismatchError,
  executionSelections,
  faceRegistrationRequest,
  isFaceRegistrationGone,
  registerFace,
  startExecution,
  useGuide,
  type GuideStepModel,
} from "@/features/guide";
import { GlassPanel, LiveNote, LiveTag, RoundBack, useLiveState } from "@/features/live";
import {
  emptyDraft,
  ProductSheet,
  type PouchItem,
  type ProductDraft,
  usePouchSync,
} from "@/features/pouch";
import { runHref, useSession, type Choice, type MatchKind } from "@/features/session";
import { ApiError, errorMessage } from "@/lib/api";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { cn } from "@/lib/utils";

import { COMPAT_TYPES, isCompatible } from "./compat";
import {
  checkRows,
  choiceOf,
  pickCounts,
  swapList,
  userChoice,
  withChoice,
  type NoneKind,
} from "./guide-check";
import { useGuideMatch, type StepMatch } from "./match-api";
import { GROUPS, TAG_BG } from "./match-groups";
import { PouchModal } from "./pouch-modal";
import { StartModal } from "./start-modal";
import { SwapPanel } from "./swap-panel";
import { Toast } from "./toast";

const NONE_TEXT: Record<NoneKind, string> = {
  skipped: "→ 제품 생략",
  pending: "→ 내 파우치와 맞춰 보는 중",
  failed: "→ 맞춰 보지 못함",
  unsupported: "→ 맞춰 볼 제품 종류가 없음",
  NO_ITEMS: "→ 파우치가 비어 있음",
  COMPARISON_UNAVAILABLE: "→ 영상 색 정보가 없음",
  NO_SUITABLE_ITEM: "→ 파우치에 적절한 제품이 없음",
};
const NO_MATCHES = new Map<string, StepMatch>();
const groupLabel = (k: MatchKind) => GROUPS.find((g) => g.k === k)?.label;

const productText = (step: GuideStepModel) =>
  [step.product?.name, step.product?.shade].filter(Boolean).join(" ") || null;

/** 실제 가이드의 제품 체크. 서버 매칭으로 보유·대체·없음을 나누고, 사용자가 바꾼 것은 선택으로 남긴다 */
export function GuideCheck() {
  const router = useRouter();
  const { state, updateRun, isCurrentRun } = useSession();
  /** 이 화면이 떠 있는지. 늦게 온 실행 생성 응답으로 다른 화면을 옮기지 않는다 */
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const { load } = useGuide();
  const run = state.run;
  const pouchSync = usePouchSync();
  const pouchReady = !state.loggedIn || pouchSync.status === "ready";
  const pouch = pouchReady ? state.pouch : [];

  const [group, setGroup] = useState<MatchKind | null>(null);
  const [swapFor, setSwapFor] = useState<string | null>(null);
  const [pouchModal, setPouchModal] = useState(false);
  const [form, setForm] = useState<ProductDraft | null>(null);
  const [startAsk, setStartAsk] = useState(false);
  /** 시작 버튼이 서버 실행을 만드는 중 · 실패한 이유 */
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const toastT = useTimeout();
  const { note, reason } = useLiveState();
  useHiddenVideo();
  // 제품을 등록·수정·삭제하면 다시 맞춘다. 수정은 ID가 그대로라 항목 값 전체를 기준으로 본다
  const { load: matching, retry } = useGuideMatch(
    pouchReady ? run.guideId : null,
    JSON.stringify(pouch),
  );

  if (load.status !== "ready") return null;
  if (state.loggedIn && pouchSync.status === "error")
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
  if (state.loggedIn && !pouchReady)
    return (
      <main className="flex flex-1 items-center justify-center px-8 text-center text-white">
        내 파우치를 불러오고 있어요.
      </main>
    );
  const rows =
    matching.status === "ready"
      ? checkRows(load.guide.steps, run.choice, pouch, matching.byStep)
      : checkRows(
          load.guide.steps,
          run.choice,
          pouch,
          NO_MATCHES,
          matching.status === "loading" ? "pending" : "failed",
        );
  const counts = pickCounts(rows);
  const active = group ?? (counts.none ? "none" : counts.sub ? "sub" : "same");
  const shown = rows.filter((r) => r.pick.kind === active);
  const swapRow = rows.find((r) => r.step.stepId === swapFor) ?? null;
  const swapMatch =
    swapRow && matching.status === "ready" ? matching.byStep.get(swapRow.step.stepId) : undefined;
  const href = (path: string) => runHref(path, run.guideId);

  /** 화면에 보이는 결과로 선택을 정해 서버 실행을 만든다. 매칭이 낡았으면 다시 맞추고, 얼굴 등록이 없으면(404) 다시 등록하게 한다 */
  const start = async () => {
    if (starting) return;
    const choice = rows.reduce(
      (c, r) => (userChoice(c, r.step.stepId) ? c : withChoice(c, r.step.stepId, choiceOf(r.pick))),
      run.choice,
    );
    const faceRegistrationId = run.faceRegistrationId;
    if (matching.status !== "ready" || !faceRegistrationId) {
      setStartError("제품 맞춰 보기가 끝나면 시작할 수 있어요.");
      return;
    }
    const runId = run.id;
    const guide = load.guide;
    const create = (faceId: string) =>
      startExecution({
        guideId: guide.guideId,
        matchId: matching.matchId,
        faceRegistrationId: faceId,
        ...executionSelections(
          guide.steps.map((s) => s.stepId),
          choice,
        ),
      });
    // 응답을 기다리는 동안 화면을 떠났거나 실행이 바뀌었으면 결과를 쓰지 않는다
    const current = () => alive.current && isCurrentRun(runId);
    setStarting(true);
    setStartError(null);
    // 마지막으로 보낸 얼굴 등록. 다시 등록하면 바뀌고, 실패 원인도 이 ID로 가른다
    let faceId = faceRegistrationId;
    try {
      let executionId: string;
      try {
        executionId = await create(faceId);
      } catch (e) {
        if (!(e instanceof ExecutionMismatchError)) throw e;
        // 이 얼굴로 만든 실행이 지금 선택과 다르다: 같은 사진으로 새로 등록해 새 실행을 만든다(서버가 이전 실행을 끝낸다)
        const photo = facePhoto(runId);
        if (!photo) {
          if (!current()) return;
          setStartAsk(false);
          updateRun({ faceReg: false, faceRegistrationId: null }, runId);
          return;
        }
        const metadata = faceRegistrationRequest(guide.videoId, guide.guideId);
        faceId = (await registerFace(photo, metadata)).faceRegistrationId;
        if (current()) updateRun({ faceRegistrationId: faceId }, runId);
        executionId = await create(faceId);
      }
      if (!current()) return;
      updateRun({ choice, executionId, faceRegistrationId: faceId }, runId);
      setStartAsk(false);
      router.push(href("/tutorial/guide"));
    } catch (e) {
      if (!current()) return;
      if (e instanceof ApiError && e.code === "GUIDE_MATCH_STALE") {
        retry();
        setStartError("제품 정보가 바뀌어 다시 맞췄어요. 확인하고 다시 시작해 주세요.");
      } else if (e instanceof ApiError && e.status === 404) {
        // 404는 얼굴 등록 · 가이드 · 매칭 어느 쪽이든 같은 코드라, 얼굴 등록을 조회해 원인을 가른다
        if (await isFaceRegistrationGone(faceId)) {
          setStartAsk(false);
          updateRun({ faceReg: false, faceRegistrationId: null }, runId);
        } else {
          retry();
          setStartError(
            "가이드나 제품 매칭을 찾지 못해 다시 맞췄어요. 확인하고 다시 시작해 주세요.",
          );
        }
      } else {
        setStartError(errorMessage(e));
      }
    } finally {
      setStarting(false);
    }
  };

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
        <div className="mb-2 flex items-end justify-between gap-4 border-b border-white/12 px-8 pb-[30px]">
          <div className="flex min-w-0 flex-col gap-1.5">
            <div className="flex items-baseline gap-3.5">
              <span className="shrink-0 font-serif text-[72px] leading-[.85] text-blush italic tabular">
                {counts.same + counts.sub}
                <span className="text-[40px] text-ash">/{rows.length}</span>
              </span>
              <h1 className="font-display text-[34px] leading-[1.15] text-white">
                쓸 제품을 골라 주세요
              </h1>
            </div>
            <span className="text-[19px] leading-[1.5] text-line-2">
              {matching.status === "loading" ? (
                "내 파우치와 맞춰 보는 중이에요."
              ) : matching.status === "error" ? (
                <>
                  {matching.message}{" "}
                  <button type="button" onClick={retry} className="font-bold text-white underline">
                    다시 맞춰 보기
                  </button>
                </>
              ) : !pouch.length ? (
                "파우치가 비어 있어요. 제품을 등록하면 다시 맞춰 봐요."
              ) : counts.same + counts.sub ? (
                "같은 제품은 보유, 색이 가까운 제품은 대체로 골라 두었어요. 눌러서 바꿀 수 있어요."
              ) : (
                "추천할 제품을 찾지 못했어요. 쓸 제품이 있으면 직접 선택해 주세요."
              )}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setPouchModal(true)}
            className="flex h-[52px] shrink-0 items-center gap-2 rounded-full border border-white/25 px-5 text-[17px] font-bold whitespace-nowrap text-white"
          >
            <Plus className="size-[18px]" strokeWidth={2.6} aria-hidden />
            제품 등록
          </button>
        </div>

        <div
          className="mx-8 grid grid-cols-3 gap-1.5 rounded-[26px] border border-white/12 bg-white/8 p-1.5"
          role="tablist"
        >
          {GROUPS.map(({ k, label, dot }) => {
            const on = active === k;
            return (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setGroup(k)}
                className={cn(
                  "flex h-[76px] items-center gap-3 rounded-[20px] px-5 transition-[background,box-shadow]",
                  on ? cn(TAG_BG[k], "shadow-float") : "hover:bg-white/8",
                )}
              >
                {on ? (
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-ink text-[#fff]">
                    <Check className="size-4" strokeWidth={3.2} aria-hidden />
                  </span>
                ) : (
                  <span className="size-3.5 shrink-0 rounded-full" style={{ background: dot }} />
                )}
                <span
                  className={cn(
                    "min-w-0 flex-1 text-left text-[24px] font-extrabold",
                    on ? "text-ink" : "text-white",
                  )}
                >
                  {label}
                </span>
                <span
                  className={cn(
                    "font-serif text-[48px] leading-none tabular",
                    on ? "text-ink" : "text-line-2",
                  )}
                >
                  {counts[k]}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto overscroll-contain px-8">
          {shown.length === 0 ? (
            <div className="py-10 text-center text-[20px] font-semibold text-ash">
              {groupLabel(active)} 단계가 없어요
            </div>
          ) : (
            shown.map(({ step, pick }) => {
              const product = productText(step);
              const mine = pick.kind === "none" ? null : pick.item;
              return (
                <div
                  key={step.stepId}
                  data-step={step.stepId}
                  className="flex min-h-[136px] shrink-0 animate-fade items-center gap-6 rounded-[28px] bg-white/90 px-6 py-6 pl-[26px] text-ink shadow-float backdrop-blur-md mirror:shadow-[inset_0_0_0_2px_var(--color-line-2)]"
                >
                  <span
                    className={cn(
                      "size-20 shrink-0 rounded-full",
                      mine?.color ? "ring-4 ring-mint" : "border-[2.5px] border-dashed border-ash",
                    )}
                    style={mine?.color ? { background: mine.color } : undefined}
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                    <span className="flex min-w-0 items-center gap-2">
                      <span
                        className={cn(
                          "flex h-[26px] shrink-0 items-center rounded-full px-2.5 text-[14px] leading-none font-extrabold text-ink",
                          TAG_BG[pick.kind],
                        )}
                      >
                        {groupLabel(pick.kind)}
                      </span>
                      <span className="truncate text-[18px] font-semibold text-mute">
                        STEP {step.order} · {step.label}
                      </span>
                    </span>
                    <span
                      className={cn(
                        "truncate leading-[1.25] font-bold",
                        product ? "text-[26px] text-ink" : "text-[21px] text-mute",
                      )}
                    >
                      {product ?? "영상에서 제품 정보를 찾지 못했어요"}
                    </span>
                    {mine ? (
                      <span className="truncate text-[19px] font-bold text-navy">
                        → {mine.brand} {mine.name}
                        {mine.shade && ` ${mine.shade}`}
                      </span>
                    ) : (
                      pick.kind === "none" && (
                        <span className="text-[19px] font-bold text-mute">
                          {NONE_TEXT[pick.reason]}
                        </span>
                      )
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => setSwapFor(step.stepId)}
                    className="flex h-[60px] shrink-0 items-center rounded-full bg-cream-3 px-6 text-[19px] font-bold whitespace-nowrap text-ink hover:bg-line"
                  >
                    {mine ? "바꾸기" : "선택"}
                  </button>
                </div>
              );
            })
          )}
        </div>

        {reason === "error" && (
          <LiveNote note={note} className="relative inset-x-auto top-auto mx-8 shrink-0" />
        )}
        <div className="flex shrink-0 items-center gap-2.5 px-8">
          <RoundBack onClick={() => router.push(href("/preview"))} label="미리보기로" />
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
        busy={starting}
        error={startError}
        onStart={() => void start()}
        onClose={() => {
          setStartAsk(false);
          setStartError(null);
        }}
      />

      {form && <ProductSheet draft={form} onClose={() => setForm(null)} onSaved={onSaved} />}
    </main>
  );
}
