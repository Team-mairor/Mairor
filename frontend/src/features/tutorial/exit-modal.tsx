"use client";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";

/** 튜토리얼 종료 확인 */
export function ExitModal({
  open,
  onQuit,
  onClose,
}: {
  open: boolean;
  onQuit: () => void;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      className="flex flex-col gap-7 rounded-[32px] px-9 pt-10 pb-8 text-ink"
    >
      <div className="flex flex-col gap-3">
        <h2 className="font-display text-[34px] leading-[1.25]">튜토리얼을 종료할까요?</h2>
        <p className="text-[19px] leading-[1.55] text-pretty text-mute">
          완료하지 않으면 기록과 사진이 남지 않아요.
        </p>
      </div>
      <div className="flex gap-3">
        <PillButton variant="line" size="cta" onClick={onQuit} className="flex-1">
          종료
        </PillButton>
        <PillButton size="cta" onClick={onClose} className="flex-1">
          계속하기
        </PillButton>
      </div>
    </Modal>
  );
}
