"use client";

import { Volume2, VolumeX, X } from "lucide-react";

import type { GuideStepInfo } from "@/features/session";
import { cn } from "@/lib/utils";

/** 튜토리얼 상단: 나가기·음성 안내·단계 진행바. 준비 카드(z-[4]) 위에 둬서 카드가 떠 있어도 누를 수 있다 */
export function TutorialTopBar({
  steps,
  step,
  voice,
  onExit,
  onToggleVoice,
  onGoStep,
}: {
  steps: GuideStepInfo[];
  step: number;
  voice: boolean;
  onExit: () => void;
  onToggleVoice: () => void;
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
      <button
        type="button"
        onClick={onToggleVoice}
        aria-pressed={voice}
        aria-label={voice ? "음성 안내 끄기" : "음성 안내 켜기"}
        className={cn(
          "flex size-12 shrink-0 items-center justify-center rounded-full border border-white/15",
          voice ? "bg-white text-navy" : "bg-night/80 text-white",
        )}
      >
        {voice ? (
          <Volume2 className="size-[20px]" strokeWidth={2.2} aria-hidden />
        ) : (
          <VolumeX className="size-[20px]" strokeWidth={2.2} aria-hidden />
        )}
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
