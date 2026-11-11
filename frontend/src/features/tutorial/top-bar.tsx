"use client";

import { X } from "lucide-react";

import type { GuideStepInfo } from "@/features/session";
import { cn } from "@/lib/utils";

/** 튜토리얼 상단: 나가기·단계 진행바. 준비 카드(z-[4]) 위에 둬서 카드가 떠 있어도 누를 수 있다 */
export function TutorialTopBar({
  steps,
  step,
  reachable,
  onExit,
  onGoStep,
}: {
  steps: Pick<GuideStepInfo, "stepId" | "short">[];
  step: number;
  /** 눌러서 갈 수 있는 마지막 단계. 앞 단계 사진이 모두 있어야 그 뒤로 갈 수 있다 */
  reachable: number;
  onExit: () => void;
  onGoStep: (i: number) => void;
}) {
  return (
    <div className="absolute inset-x-5 top-5 z-[5] flex items-center gap-3.5">
      <button
        type="button"
        onClick={onExit}
        className="flex h-12 shrink-0 items-center gap-2 rounded-full border border-white/15 bg-night/80 py-0 pr-[18px] pl-3 text-[16px] font-bold whitespace-nowrap text-white hover:bg-night/95"
      >
        <X className="size-[18px]" strokeWidth={2.4} aria-hidden />
        나가기
      </button>
      <div className="flex h-12 min-w-0 flex-1 items-center gap-3.5 rounded-full border border-white/15 bg-night/80 px-[18px]">
        <div
          className="flex min-w-0 flex-1 gap-1"
          role="progressbar"
          aria-valuenow={step + 1}
          aria-valuemax={steps.length}
        >
          {steps.map((s, i) => (
            <button
              key={s.stepId}
              type="button"
              onClick={() => onGoStep(i)}
              disabled={i > reachable}
              aria-label={`${i + 1}단계 ${s.short}`}
              className={cn(
                "h-1.5 flex-1 rounded-full transition-colors",
                i < step ? "bg-navy" : i === step ? "bg-ice" : "bg-line-2",
              )}
            />
          ))}
        </div>
        <span className="font-serif text-[24px] leading-none whitespace-nowrap text-white tabular">
          {step + 1} / {steps.length}
        </span>
      </div>
    </div>
  );
}
