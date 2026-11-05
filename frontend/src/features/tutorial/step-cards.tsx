import { CircleCheck, Lightbulb, TriangleAlert } from "lucide-react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import {
  REF_STATE_LABEL,
  type GuideStepInfo,
  type MatchResult,
  type RefState,
} from "@/features/session";
import { cn } from "@/lib/utils";

/** 단계에 보여 줄 영상 속 제품 */
export interface StepProduct {
  /** 짧은 이름 (제품 칩) */
  name: string;
  /** 브랜드까지 붙인 이름 (준비 카드) */
  full: string;
  shade: string | null;
  /** 제품 색. 모르면 null */
  color: string | null;
  state: RefState | null;
}

/** 튜토리얼 동작 한 장. 팁·주의와 끝내는 기준이 있으면 그 아래 붙인다 */
export function ActCard({
  n,
  act,
  doneWhen,
}: {
  n: number;
  act: GuideStepInfo["acts"][number];
  doneWhen: string | null;
}) {
  return (
    <div className="flex animate-fade gap-3.5 rounded-[24px] bg-white/10 px-4 py-4">
      <span className="flex size-[34px] shrink-0 items-center justify-center rounded-full bg-ice text-[17px] font-extrabold text-ink tabular">
        {n}
      </span>
      <div className="flex min-w-0 flex-col gap-2 pt-0.5">
        <span className="text-[24px] leading-[1.3] font-bold tracking-[-.01em] text-pretty text-white">
          {act.text}
        </span>
        {act.tip && (
          <span
            className={cn(
              "flex items-start gap-2 text-[17px] leading-[1.45] text-pretty",
              act.tip.kind === "caution" ? "text-blush" : "text-line-2",
            )}
          >
            {act.tip.kind === "caution" ? (
              <TriangleAlert className="mt-0.5 size-[18px] shrink-0" aria-label="주의" />
            ) : (
              <Lightbulb className="mt-0.5 size-[18px] shrink-0" aria-label="팁" />
            )}
            {act.tip.text}
          </span>
        )}
        {doneWhen && (
          <span className="flex items-start gap-2 text-[17px] leading-[1.45] text-pretty text-mint">
            <CircleCheck className="mt-0.5 size-[18px] shrink-0" aria-label="끝내는 기준" />
            {doneWhen}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * 튜토리얼 단계 준비 카드. 무엇을 집어야 하는지(제품·호수), 무엇을 할지, 언제 끝나는지 먼저 보여 준다.
 * 덮개는 z-[4]라 상단 바(z-[5])의 나가기·단계 버튼은 덮지 않는다.
 */
export function PrepCard({
  step,
  total,
  info,
  refProduct,
  match,
  onStart,
}: {
  step: number;
  /** 전체 단계 수 */
  total: number;
  info: Pick<GuideStepInfo, "title" | "acts" | "doneWhen">;
  /** 영상 속 제품. 없으면 제품 줄을 띄우지 않는다 */
  refProduct: StepProduct | null;
  /** 내 파우치와 맞춰 본 결과. 아직 맞춰 보지 않은 가이드면 null */
  match: MatchResult | null;
  onStart: () => void;
}) {
  const mine = match?.p ?? null;
  return (
    <Modal
      open
      labelledBy="prep-title"
      overlayClassName="z-[4] px-12 py-8 backdrop-blur-sm"
      className="flex max-w-[600px] flex-col gap-6 rounded-[36px] px-8 pt-8 pb-7 text-ink"
    >
      <div className="flex flex-col gap-1.5">
        <span className="font-label text-[14px] font-semibold tracking-[.14em] text-mute">
          STEP {String(step + 1).padStart(2, "0")} / {total}
        </span>
        <h2 id="prep-title" className="font-display text-[36px] leading-[1.2]">
          {info.title}
        </h2>
      </div>

      <div className="flex flex-col gap-3 rounded-[24px] border border-line p-4">
        <div className="flex items-center gap-4">
          <span
            className={cn(
              "size-14 shrink-0 rounded-full",
              mine
                ? "border-[3px] border-white ring-1 ring-line"
                : "border-[2.5px] border-dashed border-ash",
            )}
            style={mine ? { background: mine.color ?? "#fff" } : undefined}
          />
          <div className="flex min-w-0 flex-col gap-0.5">
            <span className="text-[14px] font-semibold text-navy">
              {!match
                ? "제품 매칭 전이에요"
                : match.kind === "same"
                  ? "이 제품을 준비해 주세요 · 내 파우치"
                  : match.kind === "sub"
                    ? "이 제품을 준비해 주세요 · 대체 제품"
                    : "내 파우치에 맞는 제품이 없어요"}
            </span>
            {mine ? (
              <>
                <span className="text-[20px] leading-tight font-bold">
                  {mine.brand} {mine.name}
                </span>
                {mine.shade && <span className="text-[16px] text-mute">{mine.shade}</span>}
              </>
            ) : (
              <span className="text-[17px] leading-[1.45] text-pretty text-mute">
                {match
                  ? "설명을 보고 따라 하거나 건너뛸 수 있어요"
                  : "영상 속 제품을 참고해 준비해 주세요"}
              </span>
            )}
          </div>
        </div>
        {refProduct && match?.kind !== "same" && (
          <div className="flex items-center gap-2 border-t border-line pt-3 text-[15px] text-mute">
            <span
              className={cn(
                "size-5 shrink-0 rounded-full",
                refProduct.color ? "ring-1 ring-line" : "border border-dashed border-ash",
              )}
              style={refProduct.color ? { background: refProduct.color } : undefined}
            />
            <span className="min-w-0 truncate">
              영상 속 제품 · {refProduct.full}
              {refProduct.shade && ` ${refProduct.shade}`}
            </span>
            {refProduct.state && (
              <span className="shrink-0 rounded-full border border-dashed border-navy px-2 text-[13px] text-navy">
                {REF_STATE_LABEL[refProduct.state]}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-2.5">
        <span className="text-[15px] font-semibold text-mute">할 일 {info.acts.length}가지</span>
        <ol className="flex flex-col gap-2">
          {info.acts.map((a, i) => (
            <li key={a.text} className="flex items-start gap-3 text-[19px] leading-[1.4]">
              <span className="mt-px flex size-7 shrink-0 items-center justify-center rounded-full bg-cream text-[15px] font-extrabold text-navy tabular">
                {i + 1}
              </span>
              {a.text}
            </li>
          ))}
        </ol>
        {info.doneWhen && (
          <span className="mt-1 flex items-start gap-2 text-[17px] leading-[1.45] text-navy">
            <CircleCheck className="mt-0.5 size-[18px] shrink-0" aria-label="끝내는 기준" />
            {info.doneWhen}
          </span>
        )}
      </div>

      <PillButton size="cta" trailing onClick={onStart}>
        시작하기
      </PillButton>
    </Modal>
  );
}
