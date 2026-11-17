import { Plus } from "lucide-react";

import type { MatchLoad } from "@/domain/check";

/** 제품 체크 머리말. 맞춘 개수와 맞춰 보는 상태 안내, 제품 등록 버튼 */
export function CheckHeader({
  matched,
  total,
  matching,
  pouchEmpty,
  onRetry,
  onRegister,
}: {
  /** 보유 + 대체로 정해진 단계 수 */
  matched: number;
  total: number;
  matching: MatchLoad;
  pouchEmpty: boolean;
  onRetry: () => void;
  onRegister: () => void;
}) {
  return (
    <div className="mb-2 flex items-end justify-between gap-4 border-b border-white/12 px-8 pb-[30px]">
      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex items-baseline gap-3.5">
          <span className="shrink-0 font-serif text-[72px] leading-[.85] text-blush italic tabular">
            {matched}
            <span className="text-[40px] text-ash">/{total}</span>
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
              <button type="button" onClick={onRetry} className="font-bold text-white underline">
                다시 맞춰 보기
              </button>
            </>
          ) : pouchEmpty ? (
            "파우치가 비어 있어요. 제품을 등록하면 다시 맞춰 봐요."
          ) : matched ? (
            "같은 제품은 보유, 색이 가까운 제품은 대체로 골라 두었어요. 눌러서 바꿀 수 있어요."
          ) : (
            "추천할 제품을 찾지 못했어요. 쓸 제품이 있으면 직접 선택해 주세요."
          )}
        </span>
      </div>
      <button
        type="button"
        onClick={onRegister}
        className="flex h-[52px] shrink-0 items-center gap-2 rounded-full border border-white/25 px-5 text-[17px] font-bold whitespace-nowrap text-white"
      >
        <Plus className="size-[18px]" strokeWidth={2.6} aria-hidden />
        제품 등록
      </button>
    </div>
  );
}
