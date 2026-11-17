import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { DensityMeter } from "./density-meter";
import { ActCard } from "./step-cards";
import { enteredStepNotice, type EnteredStep, type TutorialStep } from "./tutorial-steps";

export interface StepMeter {
  /** 게이지를 띄우는 단계다 */
  show: boolean;
  /** 막대 옆에 보이는 글자. 없으면 숨긴다 */
  text: string | null;
  /** 막대 값(0~100). 아직 못 쟀으면 null */
  value: number | null;
  color: string;
  /** 카메라가 잠깐 못 재서 회색으로 비운다 */
  blocked: boolean;
}

/** 밝은 카메라 영상 위에서도 제목과 할 일이 읽히도록 어두운 배경을 둔 단계 안내 카드 */
export function StepPanel({
  info,
  groupNumber,
  groupDetail,
  flash,
  meter,
  debug,
}: {
  info: TutorialStep;
  /** 상단 바 기준 몇 번째 묶음인지(1부터) */
  groupNumber: number;
  /** 묶음 안 위치. 한 단계뿐인 묶음이면 null */
  groupDetail: string | null;
  /** 준비 카드 없이 들어온 단계에서 잠깐 보이는 강조 */
  flash: EnteredStep | null;
  meter: StepMeter;
  /** 개발 도구에서 켠 게이지 디버그 */
  debug?: ReactNode;
}) {
  // 설명이 길면 얼굴을 가려 접을 수 있게 하고, 다음 단계로 가도 고른 상태를 둔다
  const [actsOpen, setActsOpen] = useState(true);
  const shownActs = info.acts.map((_, i) => i);
  return (
    <div
      className={cn(
        "-mx-3 flex flex-col gap-3.5 rounded-[22px] bg-night/85 px-4 py-4 shadow-modal backdrop-blur-xl transition-[background,box-shadow] duration-500",
        flash && "bg-night/95 ring-2 ring-blush",
      )}
    >
      {flash && (
        <span role="status" className="text-[17px] font-bold text-blush">
          {enteredStepNotice(flash)}
        </span>
      )}
      <div className="flex items-end gap-3">
        <span className="shrink-0 font-serif text-[34px] leading-[.9] text-blush italic tabular">
          {String(groupNumber).padStart(2, "0")}
        </span>
        <h1 className="font-display text-[26px] leading-[1.15] text-white">{info.title}</h1>
        {groupDetail && (
          <span className="shrink-0 text-[15px] text-line-2 tabular">{groupDetail}</span>
        )}
        {meter.show && meter.text && (
          <span
            className="ml-auto shrink-0 text-[20px] leading-tight font-extrabold whitespace-nowrap transition-colors"
            style={{ color: meter.color }}
          >
            {meter.text}
          </span>
        )}
        {shownActs.length > 0 && (
          <button
            type="button"
            onClick={() => setActsOpen((open) => !open)}
            aria-expanded={actsOpen}
            aria-controls="tutorial-acts"
            aria-label={actsOpen ? "설명 접기" : "설명 펴기"}
            className={cn(
              "flex size-10 shrink-0 items-center justify-center self-start rounded-full bg-white/10 text-white hover:bg-white/20",
              !(meter.show && meter.text) && "ml-auto",
            )}
          >
            <ChevronDown
              className={cn("size-6 transition-transform", !actsOpen && "rotate-180")}
              strokeWidth={2.4}
              aria-hidden
            />
          </button>
        )}
      </div>
      {/* 단계의 동작을 모두 카드로 띄운다. 접으면 제목·게이지만 남긴다. */}
      {actsOpen && (
        <div id="tutorial-acts" className="flex flex-col gap-2">
          {shownActs.map((i) => (
            <ActCard
              key={info.acts[i].text}
              n={i + 1}
              act={info.acts[i]}
              doneWhen={i === info.acts.length - 1 ? info.doneWhen : null}
            />
          ))}
        </div>
      )}

      {meter.show && (
        <DensityMeter value={meter.value} color={meter.color} blocked={meter.blocked} />
      )}
      {debug}
    </div>
  );
}
