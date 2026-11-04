import { cn } from "@/lib/utils";

const FLOW = ["영상 선택", "분석", "미리보기", "제품 체크"];
const FLOW_EN = ["REFERENCE", "ANALYZE", "PREVIEW", "CHECK"];

/** 따라 하기 흐름 4단계 표시 (영상 선택 → 분석 → 미리보기 → 제품 체크) */
export function FlowSteps({ step, ready = false }: { step: 0 | 1 | 2 | 3; ready?: boolean }) {
  return (
    <div className="mb-[18px] flex shrink-0 items-center justify-between gap-4">
      <span className="font-label text-[19px] font-bold tracking-[.14em] text-navy">
        STEP {step + 1} OF 4 — {ready && step === 1 ? "READY" : FLOW_EN[step]}
      </span>
      <div className="flex items-center gap-1.5" aria-label={`${FLOW[step]} 단계`}>
        {FLOW.map((l, i) => (
          <span
            key={l}
            className={cn(
              "h-2 rounded-full transition-[width,background]",
              i === step ? "w-8" : "w-2",
              i <= step ? "bg-navy" : "bg-line-2",
            )}
          />
        ))}
      </div>
    </div>
  );
}
