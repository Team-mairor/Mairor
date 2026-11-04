/** 연하게~진하게 게이지와 레퍼런스 위치선 */
export function DensityMeter({
  value,
  color,
  blocked,
}: {
  /** 0~100 */
  value: number;
  color: string;
  /** 측정할 수 없는 상태면 비운다 */
  blocked: boolean;
}) {
  return (
    <div className="flex items-center gap-3 text-[13px] font-semibold text-line-2">
      <span>연하게</span>
      <div className="relative h-2.5 flex-1">
        <div className="absolute inset-0 rounded-full bg-white/10" />
        <span
          className="absolute top-0 bottom-0 left-0 rounded-full transition-[width,background] duration-400"
          style={{ width: blocked ? "0%" : `${value}%`, background: color }}
        />
        {/* 레퍼런스 위치선. 어두운 게이지 위라 미러필름 모드에서도 흰색 그대로 둔다(data-dark) */}
        <span
          data-dark
          className="absolute -top-1.5 -bottom-1.5 left-[53.5%] -ml-[1.5px] w-[3px] rounded-sm bg-white"
        />
      </div>
      <span>진하게</span>
    </div>
  );
}
