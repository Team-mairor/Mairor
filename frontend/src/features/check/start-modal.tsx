"use client";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { cn } from "@/lib/utils";

/** 제품 체크 시작 확인 */
export function StartModal({
  open,
  missing,
  noun = "없는 제품",
  counts,
  onRecheck,
  onStart,
  onClose,
  busy = false,
  error = null,
}: {
  open: boolean;
  /** 제품을 생략할 단계 */
  missing: { key: string; label: string; color: string | null }[];
  noun?: string;
  /** 가이드 시작 전 현재 파우치 매칭 결과 */
  counts: { same: number; sub: number; none: number };
  /** 없음 목록으로 돌아가 다시 확인 */
  onRecheck: () => void;
  onStart: () => void;
  onClose: () => void;
  /** 실제 가이드는 시작 버튼이 서버 실행을 만든다. 그동안 버튼을 막는다 */
  busy?: boolean;
  /** 시작에 실패한 이유. 있으면 버튼 위에 보이고 다시 누를 수 있다 */
  error?: string | null;
}) {
  const n = missing.length;
  return (
    <Modal
      open={open}
      onClose={onClose}
      className="flex max-w-none flex-col gap-7 rounded-[32px] px-9 pt-10 pb-8 text-ink"
    >
      <div className="flex flex-col gap-3">
        <h2 className="font-display text-[36px] leading-[1.25]">
          {n ? `${noun} ${n}개는 생략할까요?` : "이대로 시작할까요?"}
        </h2>
        <p className="text-[20px] leading-[1.5] text-mute">
          {n ? "이 단계들은 설명만 보여 드리고 넘어가요. " : ""}시작하면 제품을 바꿀 수 없어요.
        </p>
        <p className="text-[17px] font-semibold text-mute">
          보유 제품 {counts.same}단계 · 비슷한 제품 {counts.sub}단계 · 없는 제품 {counts.none}단계
        </p>
      </div>
      {n > 0 && (
        <div className="-mx-1 flex max-h-[420px] min-h-0 flex-col gap-2.5 overflow-y-auto px-1">
          {missing.map((m) => (
            <div
              key={m.key}
              className="flex shrink-0 items-center gap-4 rounded-[22px] border-2 border-dashed border-ash px-5 py-4"
            >
              <span
                className={cn(
                  "size-12 shrink-0 rounded-full",
                  !m.color && "border-[2.5px] border-dashed border-ash",
                )}
                style={m.color ? { background: m.color } : undefined}
              />
              <span className="min-w-0 flex-1 truncate text-[22px] font-bold">{m.label}</span>
            </div>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="text-[18px] leading-[1.5] text-error">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <PillButton variant="line" size="hero" onClick={onRecheck} disabled={busy}>
          다시 확인
        </PillButton>
        <PillButton
          size="hero"
          trailing
          onClick={onStart}
          disabled={busy}
          className="ml-auto min-w-[300px]"
        >
          {busy ? "시작하는 중" : n ? "건너뛰고 시작" : "시작하기"}
        </PillButton>
      </div>
    </Modal>
  );
}
