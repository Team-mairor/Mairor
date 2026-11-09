"use client";

import { Check, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { useHiddenVideo } from "@/features/face";
import { useGuide, type GuideStepModel } from "@/features/guide";
import { GlassPanel, LiveNote, LiveTag, RoundBack, useLiveState } from "@/features/live";
import { emptyDraft, ProductSheet, type PouchItem, type ProductDraft } from "@/features/pouch";
import { runHref, useSession, type Choice } from "@/features/session";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { cn } from "@/lib/utils";

import { COMPAT_TYPES, isCompatible } from "./compat";
import {
  candidatesFor,
  checkRows,
  markNoFit,
  pickCounts,
  withChoice,
  type PickKind,
} from "./guide-check";
import { PouchModal } from "./pouch-modal";
import { StartModal } from "./start-modal";
import { SwapPanel } from "./swap-panel";
import { Toast } from "./toast";

/** 선택 상태별 탭. 상태가 늘면 여기서 빠진 것을 타입 검사가 잡는다 */
const PICK_GROUPS: Record<PickKind, { label: string; dot: string; bg: string }> = {
  undecided: { label: "미확정", dot: "var(--color-blush)", bg: "bg-blush" },
  picked: { label: "선택", dot: "var(--color-mint)", bg: "bg-mint" },
  skipped: { label: "생략", dot: "var(--color-ash)", bg: "bg-cream-3" },
};
const PICK_TABS = Object.keys(PICK_GROUPS) as PickKind[];

const productText = (step: GuideStepModel) =>
  [step.product?.name, step.product?.shade].filter(Boolean).join(" ") || null;

/** 실제 가이드의 제품 체크. 보유·대체를 판정하지 않고 사용자가 고른 것만 남긴다. 파우치에 맞는 제품이 없는 단계는 제품을 생략한다 */
export function GuideCheck() {
  const router = useRouter();
  const { state, updateRun } = useSession();
  const { load } = useGuide();
  const run = state.run;
  const pouch = state.pouch;

  const [group, setGroup] = useState<PickKind | null>(null);
  const [swapFor, setSwapFor] = useState<string | null>(null);
  const [pouchModal, setPouchModal] = useState(false);
  const [form, setForm] = useState<ProductDraft | null>(null);
  const [startAsk, setStartAsk] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const toastT = useTimeout();
  const { note, reason } = useLiveState();
  useHiddenVideo();

  if (load.status !== "ready") return null;
  const rows = markNoFit(checkRows(load.guide.steps, run.choice, pouch), pouch);
  const noFit = rows.filter((r) => r.noFit);
  const counts = pickCounts(rows);
  const active = group ?? (counts.undecided ? "undecided" : "picked");
  const shown = rows.filter((r) => r.pick.kind === active);
  const swapRow = rows.find((r) => r.step.stepId === swapFor) ?? null;
  const href = (path: string) => runHref(path, run.guideId);

  const setChoice = (stepId: string, value: Choice | null) =>
    updateRun((prev) => ({ choice: withChoice(prev.choice, stepId, value) }), run.id);
  const closeSwap = () => setSwapFor(null);
  const showToast = (ok: boolean, text: string) => {
    setToast({ ok, text });
    toastT.set(() => setToast(null), 2800);
  };
  // 등록한 제품은 자동으로 고르지 않는다
  const onSaved = (item: PouchItem, isNew: boolean) => {
    if (!isNew) return;
    if (swapRow && isCompatible(swapRow.step, item))
      showToast(true, `'${item.name}' 등록 완료 · 목록에서 고를 수 있어요`);
    else showToast(true, `'${item.name}' 등록 완료`);
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
            list={candidatesFor(swapRow.step, pouch)}
            curId={swapRow.pick.kind === "picked" ? swapRow.pick.item.id : null}
            skipped={swapRow.pick.kind === "skipped"}
            ranked={false}
            emptyText={
              COMPAT_TYPES[swapRow.step.makeup].length
                ? `파우치에 ${COMPAT_TYPES[swapRow.step.makeup].join("·")} 종류 제품이 없어요`
                : "이 단계에 맞춰 볼 제품 종류가 아직 정해지지 않았어요"
            }
            onPick={(choice) => {
              setChoice(swapRow.step.stepId, choice);
              closeSwap();
            }}
            onClear={
              swapRow.pick.kind === "undecided" || swapRow.noFit
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
                {counts.picked}
                <span className="text-[40px] text-ash">/{rows.length}</span>
              </span>
              <h1 className="font-display text-[34px] leading-[1.15] text-white">
                쓸 제품을 골라 주세요
              </h1>
            </div>
            <span className="text-[19px] leading-[1.5] text-line-2">
              {pouch.length
                ? "영상 속 제품은 이름만 확인했어요. 내 파우치에서 직접 골라 주세요."
                : "파우치가 비어 있어요. 제품을 등록하면 고를 수 있어요."}
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
          {PICK_TABS.map((k) => {
            const g = PICK_GROUPS[k];
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
                  on ? cn(g.bg, "shadow-float") : "hover:bg-white/8",
                )}
              >
                {on ? (
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-ink text-[#fff]">
                    <Check className="size-4" strokeWidth={3.2} aria-hidden />
                  </span>
                ) : (
                  <span className="size-3.5 shrink-0 rounded-full" style={{ background: g.dot }} />
                )}
                <span
                  className={cn(
                    "min-w-0 flex-1 text-left text-[24px] font-extrabold",
                    on ? "text-ink" : "text-white",
                  )}
                >
                  {g.label}
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
              {PICK_GROUPS[active].label} 단계가 없어요
            </div>
          ) : (
            shown.map(({ step, pick, noFit: noFitRow }) => {
              const product = productText(step);
              return (
                <div
                  key={step.stepId}
                  data-step={step.stepId}
                  className="flex min-h-[136px] shrink-0 animate-fade items-center gap-6 rounded-[28px] bg-white/90 px-6 py-6 pl-[26px] text-ink shadow-float backdrop-blur-md mirror:shadow-[inset_0_0_0_2px_var(--color-line-2)]"
                >
                  <span
                    className={cn(
                      "size-20 shrink-0 rounded-full",
                      pick.kind === "picked" && pick.item.color
                        ? "ring-4 ring-mint"
                        : "border-[2.5px] border-dashed border-ash",
                    )}
                    style={
                      pick.kind === "picked" && pick.item.color
                        ? { background: pick.item.color }
                        : undefined
                    }
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                    <span className="flex min-w-0 items-center gap-2">
                      <span
                        className={cn(
                          "flex h-[26px] shrink-0 items-center rounded-full px-2.5 text-[14px] font-extrabold text-ink",
                          PICK_GROUPS[pick.kind].bg,
                        )}
                      >
                        {PICK_GROUPS[pick.kind].label}
                      </span>
                      <span className="truncate text-[18px] font-semibold text-mute">
                        STEP {step.order} · {step.label}
                      </span>
                      {product && (
                        <span className="flex h-[26px] shrink-0 items-center rounded-full border-[1.5px] border-dashed border-navy px-2.5 text-[13px] font-bold text-navy">
                          이름만 확인
                        </span>
                      )}
                    </span>
                    <span
                      className={cn(
                        "truncate leading-[1.25] font-bold",
                        product ? "text-[26px] text-ink" : "text-[21px] text-mute",
                      )}
                    >
                      {product ?? "영상에서 제품 정보를 찾지 못했어요"}
                    </span>
                    {pick.kind === "picked" && (
                      <span className="truncate text-[19px] font-bold text-navy">
                        → {pick.item.brand} {pick.item.name}
                        {pick.item.shade && ` ${pick.item.shade}`}
                      </span>
                    )}
                    {pick.kind === "skipped" && (
                      <span className="text-[19px] font-bold text-mute">
                        {noFitRow ? "→ 파우치에 맞는 제품이 없어 생략" : "→ 제품 생략"}
                      </span>
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => setSwapFor(step.stepId)}
                    className="flex h-[60px] shrink-0 items-center rounded-full bg-cream-3 px-6 text-[19px] font-bold whitespace-nowrap text-ink hover:bg-line"
                  >
                    {pick.kind === "undecided" || noFitRow ? "고르기" : "바꾸기"}
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

      {/* 고를 수 있는데 고르지 않은 단계는 none으로 바꾸지 않는다 */}
      <StartModal
        open={startAsk}
        noun="고르지 않은 단계"
        note={
          noFit.length
            ? `파우치에 맞는 제품이 없는 ${noFit.length}단계는 제품을 생략해요.`
            : undefined
        }
        missing={rows
          .filter((r) => r.pick.kind === "undecided")
          .map((r) => ({
            key: r.step.stepId,
            label: `${r.step.label} · ${productText(r.step) ?? "제품 정보 없음"}`,
            color: null,
          }))}
        onRecheck={() => {
          setStartAsk(false);
          setGroup("undecided");
        }}
        onStart={() => {
          setStartAsk(false);
          if (noFit.length)
            updateRun(
              (prev) => ({
                choice: noFit.reduce(
                  (c, r) => withChoice(c, r.step.stepId, { kind: "none" }),
                  prev.choice,
                ),
              }),
              run.id,
            );
          router.push(href("/tutorial/guide"));
        }}
        onClose={() => setStartAsk(false)}
      />

      {form && <ProductSheet draft={form} onClose={() => setForm(null)} onSaved={onSaved} />}
    </main>
  );
}
