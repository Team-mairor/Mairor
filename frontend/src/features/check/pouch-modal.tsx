"use client";

import { ArrowLeft, Plus } from "lucide-react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { PouchReview, type PouchItem } from "@/features/pouch";

/** 제품 체크에서 시작하기 전에 내 파우치를 확인하는 모달 */
export function PouchModal({
  open,
  pouch,
  onEdit,
  onAdd,
  onClose,
}: {
  open: boolean;
  pouch: PouchItem[];
  onEdit: (item: PouchItem) => void;
  onAdd: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      label="내 파우치"
      overlayClassName="z-[8] p-8"
      className="flex max-w-none flex-col gap-[22px] p-8 text-ink"
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2.5 rounded-full bg-cream px-[18px] py-2.5 text-[17px] font-semibold">
          <span className="size-2 rounded-full bg-cyan" />내 파우치 · {pouch.length}개
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="flex size-11 items-center justify-center rounded-full border border-line"
        >
          <ArrowLeft className="size-[18px]" strokeWidth={1.8} aria-hidden />
        </button>
      </div>
      <PouchReview
        lead="시작하기 전에"
        desc="최근에 산 제품이 있다면 지금 등록해 두세요. 매칭에 바로 반영돼요."
        items={pouch}
        onEdit={onEdit}
      />
      <div className="flex gap-2.5">
        <PillButton variant="line" size="hero" onClick={onAdd}>
          <Plus className="size-[18px]" strokeWidth={2} aria-hidden />새 제품 등록
        </PillButton>
        <PillButton size="hero" trailing onClick={onClose} className="ml-auto min-w-[300px]">
          다 했어요
        </PillButton>
      </div>
    </Modal>
  );
}
