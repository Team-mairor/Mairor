import { TriangleAlert } from "lucide-react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";

/** 단계를 넘기려는데 레퍼런스보다 연할 때 더 바를지 묻는다 */
export function LackMoreModal({
  open,
  onMore,
  onSkip,
}: {
  open: boolean;
  onMore: () => void;
  onSkip: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onMore}
      className="flex flex-col gap-7 rounded-[32px] px-9 pt-10 pb-8 text-ink"
    >
      <div className="flex flex-col gap-3">
        <h2 className="font-display text-[34px] leading-[1.25]">조금 더 발라 주세요</h2>
        <p className="text-[19px] leading-[1.55] text-pretty text-mute">
          레퍼런스보다 연해요. 조금 더 바르면 더 비슷해져요.
        </p>
      </div>
      <div className="flex gap-3">
        <PillButton variant="line" size="cta" onClick={onSkip} className="flex-1">
          넘어가기
        </PillButton>
        <PillButton size="cta" onClick={onMore} className="flex-1">
          더 바르기
        </PillButton>
      </div>
    </Modal>
  );
}

/** 레퍼런스보다 훨씬 진할 때 멈추고 확인하게 한다. 배경을 눌러 닫을 수 없다 */
export function TooDarkModal({ open, onConfirm }: { open: boolean; onConfirm: () => void }) {
  return (
    <Modal
      open={open}
      label="너무 진해요"
      className="flex flex-col items-center gap-8 rounded-[32px] px-9 pt-12 pb-8 text-center text-ink"
    >
      <TriangleAlert className="size-16 text-error" strokeWidth={1.8} aria-hidden />
      <div className="flex flex-col gap-4">
        <h2 className="font-display text-[44px] leading-[1.2]">너무 진해요</h2>
        <p className="text-[21px] leading-[1.55] text-pretty text-mute">
          레퍼런스보다 훨씬 진하게 발렸어요. 휴지로 살짝 눌러 닦거나 톡톡 두드려 연하게 한 뒤 계속해
          주세요.
        </p>
      </div>
      <PillButton size="cta" onClick={onConfirm} className="w-full">
        확인했어요
      </PillButton>
    </Modal>
  );
}
