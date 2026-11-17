import { GROUPS, TAG_BG, type CheckRow, type NoneKind } from "@/domain/check";
import type { GuideStepModel } from "@/domain/guide";
import type { MatchKind } from "@/domain/session";
import { cn } from "@/lib/utils";

const NONE_TEXT: Record<NoneKind, string> = {
  skipped: "→ 제품 생략",
  pending: "→ 내 파우치와 맞춰 보는 중",
  failed: "→ 맞춰 보지 못함",
  unsupported: "→ 맞춰 볼 제품 종류가 없음",
  NO_ITEMS: "→ 파우치가 비어 있음",
  COMPARISON_UNAVAILABLE: "→ 영상 색 정보가 없음",
  NO_SUITABLE_ITEM: "→ 파우치에 적절한 제품이 없음",
};

export const groupLabel = (k: MatchKind) => GROUPS.find((g) => g.k === k)?.label;

/** 영상 속 제품을 이름과 호수로 */
export const productText = (step: GuideStepModel) =>
  [step.product?.name, step.product?.shade].filter(Boolean).join(" ") || null;

/** 제품 체크의 단계 한 줄. 영상 속 제품과 고른 내 제품을 보여 주고 바꾸기를 누르게 한다 */
export function CheckStepRow({ row, onSwap }: { row: CheckRow; onSwap: () => void }) {
  const { step, pick } = row;
  const product = productText(step);
  const mine = pick.kind === "none" ? null : pick.item;
  return (
    <div
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
            <span className="text-[19px] font-bold text-mute">{NONE_TEXT[pick.reason]}</span>
          )
        )}
      </span>
      <button
        type="button"
        onClick={onSwap}
        className="flex h-[60px] shrink-0 items-center rounded-full bg-cream-3 px-6 text-[19px] font-bold whitespace-nowrap text-ink hover:bg-line"
      >
        {mine ? "바꾸기" : "선택"}
      </button>
    </div>
  );
}
