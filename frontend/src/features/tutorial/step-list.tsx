"use client";

import { Check } from "lucide-react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { cn } from "@/lib/utils";

/** 목록 한 줄. 상단 바 칸 하나(묶음)다 */
export interface StepListItem {
  title: string;
  product: string | null;
  /** 묶음 사진을 남겼는지 */
  done: boolean;
}

/**
 * 튜토리얼 단계 목록. 아무 단계나 눌러 그 단계로 가고, 원하는 단계까지만 하고 지금 단계에서 완성할 수 있다.
 * 완성하면 지금 단계 사진을 얼굴 전체 사진으로 찍고 끝낸다.
 */
export function StepList({
  open,
  items,
  current,
  onGo,
  onFinish,
  onClose,
}: {
  open: boolean;
  items: readonly StepListItem[];
  current: number;
  onGo: (i: number) => void;
  onFinish: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      align="bottom"
      labelledBy="step-list-title"
      className="flex max-h-[85%] flex-col gap-5 text-ink"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="step-list-title" className="font-display text-[30px] leading-[1.2]">
          단계 목록
        </h2>
        <span className="text-[17px] text-mute tabular">
          {current + 1} / {items.length}
        </span>
      </div>
      <ol className="-mx-2 flex min-h-0 flex-col gap-1 overflow-y-auto">
        {items.map((item, i) => (
          <li key={i}>
            <button
              type="button"
              onClick={() => onGo(i)}
              aria-current={i === current ? "step" : undefined}
              className={cn(
                "flex w-full items-center gap-4 rounded-[18px] px-3 py-3 text-left hover:bg-cream",
                i === current && "bg-ice-pale",
              )}
            >
              <span className="w-9 shrink-0 font-serif text-[24px] leading-none text-navy tabular">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="text-[19px] leading-[1.35] font-bold">{item.title}</span>
                {item.product && (
                  <span className="truncate text-[16px] text-mute">{item.product}</span>
                )}
              </span>
              {i === current ? (
                <span className="shrink-0 rounded-full bg-navy px-3 py-1 text-[14px] font-bold text-white">
                  지금
                </span>
              ) : item.done ? (
                <Check
                  className="size-6 shrink-0 text-navy"
                  strokeWidth={2.4}
                  aria-label="사진 남김"
                />
              ) : null}
            </button>
          </li>
        ))}
      </ol>
      <div className="flex gap-3">
        <PillButton variant="line" size="cta" onClick={onClose} className="flex-1">
          닫기
        </PillButton>
        <PillButton size="cta" onClick={onFinish} className="flex-[2]">
          지금 단계에서 완성하기
        </PillButton>
      </div>
    </Modal>
  );
}
