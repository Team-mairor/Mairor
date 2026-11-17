import { PillButton } from "@/components/ui/pill-button";
import type { PendingGuide } from "@/domain/session";
import { videoThumb } from "@/domain/video";

/** 영상 검수 중이거나 끝난 가이드를 알리고, 끝났으면 바로 시작하게 한다 */
export function PendingGuideCard({
  pg,
  ready,
  onStart,
}: {
  pg: PendingGuide;
  /** guideId가 올바른 승인 가이드 */
  ready: boolean;
  onStart: () => void;
}) {
  const approved = pg.status === "approved";
  const text = ready
    ? "분석 완료 · 지금 따라 할 수 있어요"
    : approved
      ? "가이드 정보를 다시 확인해 주세요"
      : "검수 중 · 끝나면 여기서 바로 시작해요";
  return (
    <div className="flex min-w-0 shrink-0 items-center gap-[18px] rounded-3xl border border-line bg-white p-3.5">
      <span
        className="h-20 w-[120px] shrink-0 rounded-[14px] bg-cover bg-center"
        style={{
          backgroundImage: `url(${pg.ytid ? videoThumb(pg.ytid) : "/images/login-editorial.png"})`,
        }}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="font-label text-[14px] font-semibold tracking-[.14em] text-navy">
          {approved ? "READY" : "IN REVIEW"}
        </span>
        <span className="truncate font-display text-[20px] leading-[1.3] text-ink">{pg.title}</span>
        <span className="truncate text-[16px] text-mute">{text}</span>
      </div>
      {approved && (
        <PillButton size="md" className="h-14 shrink-0 text-[18px]" onClick={onStart}>
          {ready ? "따라 하기" : "다시 확인"}
        </PillButton>
      )}
    </div>
  );
}
