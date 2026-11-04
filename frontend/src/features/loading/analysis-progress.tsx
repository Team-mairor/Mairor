import { ANALYSIS_PHASES } from "@/features/video";
import { cn } from "@/lib/utils";

/** 큰 퍼센트와 단계 이름, 진행 선, 단계 6칸 */
export function AnalysisProgress({
  pct,
  phaseIdx,
  phaseEn,
  phaseLabel,
  eta,
  failed,
}: {
  pct: number;
  phaseIdx: number;
  phaseEn: string;
  phaseLabel: string;
  eta: string;
  failed: boolean;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-3.5">
      <div className="flex items-end justify-between gap-5">
        <span className="font-serif text-[120px] leading-[.8] tracking-[-.03em] text-ink tabular">
          {pct}
          <span className="text-[44px] text-navy">%</span>
        </span>
        <span className="flex flex-col items-end gap-1.5 pb-1">
          <span className="font-serif text-[32px] leading-none text-navy italic">{phaseEn}</span>
          <span className="text-[17px] whitespace-nowrap text-mute">
            {phaseLabel} · {eta}
          </span>
        </span>
      </div>
      <div className="relative h-0.5 bg-line">
        <div
          className="absolute top-0 left-0 h-0.5 bg-ink transition-[width] duration-600 ease-linear"
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute -top-1 -ml-[5px] size-2.5 rounded-full bg-cyan transition-[left] duration-600 ease-linear"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="grid grid-cols-6 gap-2">
        {ANALYSIS_PHASES.map(([en], i) => (
          <span
            key={en}
            className={cn(
              "font-label text-[15px] font-semibold tracking-[.12em] transition-colors",
              failed && i === phaseIdx ? "text-error" : i <= phaseIdx ? "text-ink" : "text-mute",
            )}
          >
            {en}
          </span>
        ))}
      </div>
    </div>
  );
}
