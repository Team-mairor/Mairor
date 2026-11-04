"use client";

import { Plus, X } from "lucide-react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { PouchReview, type PouchItem } from "@/features/pouch";

import { ProgressBar } from "./progress-bar";

/** 분석을 기다리는 동안 내 파우치를 확인하는 모달 */
export function PouchCheckModal({
  open,
  pct,
  barText,
  pouch,
  changed,
  onClose,
  onEdit,
  onAdd,
}: {
  open: boolean;
  pct: number;
  barText: string;
  pouch: PouchItem[];
  /** 이번에 제품을 새로 넣었는지. 닫기 버튼 글자가 바뀐다 */
  changed: boolean;
  onClose: () => void;
  onEdit: (item: PouchItem) => void;
  onAdd: () => void;
}) {
  return (
    <Modal
      open={open}
      label="내 파우치 확인"
      overlayClassName="z-[4] p-8"
      className="flex max-w-none flex-col overflow-hidden rounded-[32px] p-0"
    >
      <ProgressBar pct={pct} text={barText} />
      <div className="flex animate-step-in flex-col gap-[22px] px-8 pt-7 pb-8">
        <div className="flex w-full items-center justify-between gap-3">
          <span className="flex items-center gap-2.5 text-[16px] font-bold text-navy">
            <span className="flex gap-1.5">
              <span className="h-1.5 w-[22px] rounded-full bg-blush" />
              <span className="h-1.5 w-[22px] rounded-full bg-cyan" />
            </span>
            STEP 2 · 내 파우치
          </span>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto flex h-14 items-center gap-3 text-[24px] font-bold whitespace-nowrap text-ink"
          >
            {changed ? "다 했어요" : "변경 없어요"}
            <span className="flex size-11 items-center justify-center rounded-full bg-ink text-white">
              <X className="size-5" strokeWidth={3} aria-hidden />
            </span>
          </button>
        </div>
        <PouchReview
          lead="기다리는 동안"
          desc="최근에 산 제품이 있다면 지금 등록해 두세요. 분석 결과에 바로 반영돼요."
          items={pouch}
          onEdit={onEdit}
        />
        <PillButton size="hero" onClick={onAdd}>
          <Plus className="size-[22px]" strokeWidth={2.6} aria-hidden />새 제품 등록하기
        </PillButton>
      </div>
    </Modal>
  );
}
