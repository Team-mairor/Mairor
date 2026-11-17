import { IconButton } from "@/components/ui/icon-button";
import { PillButton } from "@/components/ui/pill-button";

import type { LoadingNotice } from "./loading-status";
import { ReadyStatus } from "./ready-status";

/** 로딩 화면 상단. 분석 중인지 다시 따라 하기 준비인지 알린다 */
export function LoadingHeader({
  replay,
  replayKind,
  onBack,
}: {
  replay: boolean;
  replayKind: "guide" | "report" | null;
  onBack: () => void;
}) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
      <IconButton size={44} onClick={onBack} title="영상 입력" aria-label="영상 입력" />
      <span className="font-serif text-[28px] leading-none text-navy italic">
        {replay ? "Ready" : "Analyzing"}
      </span>
      <span className="text-[17px] text-mute">
        {replay
          ? replayKind === "guide"
            ? "바로 따라 하기 준비"
            : "다시 따라 하기 준비"
          : "영상 분석 중"}
      </span>
    </header>
  );
}

/** 분석이 멈췄거나 검수 중일 때 보여 주는 안내 카드 */
export function LoadingNoticeCard({
  notice,
  retryError,
}: {
  notice: LoadingNotice;
  /** 다시 시도가 실패한 이유. 멈춘 작업에서만 보여 준다 */
  retryError: string | null;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-3 rounded-3xl bg-cream px-7 py-6">
      <span className="font-label text-[15px] font-semibold tracking-[.14em] text-navy">
        {notice.tag}
      </span>
      <span className="font-display text-[28px] leading-[1.3] text-pretty text-ink">
        {notice.title}
      </span>
      <span className="text-[18px] leading-[1.5] text-pretty text-mute">{notice.sub}</span>
      {retryError && (
        <span role="alert" className="text-[17px] leading-[1.5] text-pretty text-error">
          {retryError}
        </span>
      )}
    </div>
  );
}

/** 로딩 화면 하단. 준비 상태와 파우치 확인, 다음으로 가는 큰 버튼 */
export function LoadingFooter({
  readyItems,
  saveError,
  onPouch,
  failed,
  cta,
  onSelect,
}: {
  readyItems: Parameters<typeof ReadyStatus>[0]["items"];
  saveError: string | null;
  /** 파우치 확인 버튼. 없으면 버튼을 숨긴다 */
  onPouch: (() => void) | null;
  /** 분석이 멈췄을 때만 값이 있다. 다시 시도할 수 있으면 다시 시도 버튼을 함께 보인다 */
  failed: { canRetry: boolean; retrying: boolean; onRetry: () => void } | null;
  cta: { label: string; disabled: boolean; onClick: () => void };
  onSelect: () => void;
}) {
  return (
    <div className="flex shrink-0 flex-col gap-4 border-t border-line px-10 pt-5 pb-7">
      <ReadyStatus items={readyItems} />
      {saveError && (
        <p role="alert" className="text-[17px] text-error">
          {saveError}
        </p>
      )}
      {onPouch && (
        <PillButton variant="line" size="hero" onClick={onPouch}>
          내 파우치 확인 / 추가
        </PillButton>
      )}
      {failed ? (
        <div className="flex gap-3">
          {failed.canRetry && (
            <PillButton
              size="hero"
              onClick={failed.onRetry}
              disabled={failed.retrying}
              className="flex-1"
            >
              {failed.retrying ? "다시 시도하는 중" : "다시 시도"}
            </PillButton>
          )}
          <PillButton variant="line" size="hero" onClick={onSelect} className="flex-1">
            다른 영상 고르기
          </PillButton>
        </div>
      ) : (
        <PillButton size="hero" onClick={cta.onClick} disabled={cta.disabled}>
          {cta.label}
        </PillButton>
      )}
    </div>
  );
}
