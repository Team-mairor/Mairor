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

/** 연하게~진하게 게이지와 레퍼런스 위치선 */
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
      className="flex flex-col gap-1.5 text-[13px] font-bold text-white"
    >
      <div className="grid grid-cols-3 items-center text-[12px] font-bold text-white/85">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border-2 border-white bg-ice" aria-hidden />내 위치
        </span>
        <span className="flex items-center justify-center gap-1.5">목표</span>
      </div>
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-3">
        <span>연하게</span>
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
            data-dark
            className="absolute top-0.5 h-5 w-[3px] -translate-x-1/2 rounded-sm bg-white"
            style={{ left: `${GAUGE_REFERENCE}%` }}
          />
          <span
            data-current
            data-measuring={current === null || undefined}
            className={`absolute top-0 size-6 -translate-x-1/2 rounded-full border-[4px] border-white bg-ice shadow-md transition-[left,opacity] duration-250 ${current === null ? "animate-pulse" : ""}`}
            style={{ left: `${visual}%` }}
          >
            <span className="sr-only">{current === null ? "측정 시작점" : "현재 위치"}</span>
          </span>
        </div>
        <span>진하게</span>
      </div>
    </div>
  );
}
