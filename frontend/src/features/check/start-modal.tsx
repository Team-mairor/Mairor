"use client";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { cn } from "@/lib/utils";

/** 제품 체크 시작 확인 */
export function StartModal({
  open,
  missing,
  noun = "없는 제품",
  onRecheck,
  onStart,
  onClose,
}: {
  open: boolean;
  /** 제품 없이 진행할 단계 */
  missing: { key: string; label: string; color: string | null }[];
  noun?: string;
  /** 없음 목록으로 돌아가 다시 확인 */
  onRecheck: () => void;
  onStart: () => void;
  onClose: () => void;
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
          {n ? `${noun} ${n}개는` : "이대로"}
          <br />
          {n ? "건너뛰고 시작할까요?" : "시작할까요?"}
        </h2>
        <p className="text-[20px] leading-[1.5] text-mute">
          {n ? "이 단계들은 설명만 보여 드리고 넘어가요. " : ""}시작하면 제품을 바꿀 수 없어요.
        </p>
      </div>
      {n > 0 && (
        <div className="flex flex-col gap-2.5">
          {missing.map((m) => (
            <div
              key={m.key}
              className="flex items-center gap-4 rounded-[22px] border-2 border-dashed border-ash px-5 py-4"
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
      <div className="flex gap-3">
        <PillButton variant="line" size="hero" onClick={onRecheck}>
          다시 확인
        </PillButton>
        <PillButton size="hero" trailing onClick={onStart} className="ml-auto min-w-[300px]">
          {n ? "건너뛰고 시작" : "시작하기"}
        </PillButton>
      </div>
    </Modal>
  );
}
