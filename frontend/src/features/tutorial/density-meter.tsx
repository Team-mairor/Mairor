import { GAUGE_DARKER_FROM, GAUGE_SIMILAR_FROM } from "./use-smoothed-gauge";

/** 레퍼런스만큼 바른 자리(0~100). 막대는 내 화장 효과 ÷ 레퍼런스 효과 × 50이다 */
export const GAUGE_REFERENCE = 50;
/** 0도 트랙 안에서 시작점과 최소 채움이 보이게 하는 화면 위치 */
export const GAUGE_START = 4;
/** 목표 전 구간을 조금 넉넉하게 보이되 0과 목표 위치는 그대로 두는 표시 곡선 */
const GAUGE_EASE_POWER = 0.8;

export function gaugeVisualValue(value: number): number {
  const current = Math.min(Math.max(value, 0), 100);
  if (current === 0 || current >= GAUGE_REFERENCE) return current;
  const eased = GAUGE_REFERENCE * (current / GAUGE_REFERENCE) ** GAUGE_EASE_POWER;
  return Math.round(eased * 100) / 100;
}

/** 연해요~진해요 게이지와 목표 구간 띠 */
export function DensityMeter({
  value,
  color,
  blocked,
}: {
  /** 0~100. 아직 한 번도 재지 못했으면 null */
  value: number | null;
  color: string;
  /** 측정 불가는 data-blocked로 표시하고 마지막 위치는 유지한다 */
  blocked: boolean;
}) {
  const current = value === null ? null : Math.min(Math.max(value, 0), 100);
  const visualCurrent = current === null ? null : gaugeVisualValue(current);
  const visual = Math.max(visualCurrent ?? 0, GAUGE_START);
  // 「비슷해요」로 보는 목표 구간. 막대와 같은 표시 곡선으로 그려 위치가 맞는다
  const bandFrom = gaugeVisualValue(GAUGE_SIMILAR_FROM);
  const bandTo = gaugeVisualValue(GAUGE_DARKER_FROM);
  return (
    <div
      role="meter"
      data-blocked={blocked || undefined}
      aria-label="현재 화장 진하기"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={visualCurrent ?? undefined}
      aria-valuetext={
        visualCurrent === null ? "측정 중" : `현재 ${Math.round(visualCurrent)}, 목표 50`
      }
      className="flex flex-col gap-1.5 pt-3.5 text-[13px] font-bold text-white"
    >
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3">
        <span>연해요</span>
        <div className="relative h-6 min-w-0">
          <div
            data-track
            className="absolute top-1.5 right-0 left-0 h-3 rounded-full border border-white bg-[#33446F]"
          />
          <span
            data-fill
            className="absolute top-1.5 left-0 h-3 rounded-full transition-[width,background,opacity] duration-250"
            style={{ width: `${visual}%`, background: color }}
          />
          <span
            data-target-band
            aria-hidden
            className="absolute top-1.5 h-3 rounded-sm bg-white/25"
            style={{ left: `${bandFrom}%`, width: `${bandTo - bandFrom}%` }}
          />
          <span
            data-target-label
            data-dark
            aria-hidden
            className="absolute -top-3.5 -translate-x-1/2 text-[12px] font-bold text-white/85"
            style={{ left: `${(bandFrom + bandTo) / 2}%` }}
          >
            목표
          </span>
          <span
            data-current
            data-measuring={current === null || undefined}
            className={`absolute top-0 size-6 -translate-x-1/2 rounded-full border-[4px] border-white bg-ice shadow-md transition-[left,opacity] duration-250 ${current === null ? "animate-pulse" : ""}`}
            style={{ left: `${visual}%` }}
          >
            <span className="sr-only">{current === null ? "측정 시작점" : "현재 위치"}</span>
          </span>
        </div>
        <span>진해요</span>
      </div>
    </div>
  );
}
