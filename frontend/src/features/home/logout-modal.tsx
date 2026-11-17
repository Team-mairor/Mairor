"use client";

import { Modal } from "@/components/ui/modal";
import { FieldError } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { useLogout } from "@/features/auth";

/** 잘못 눌러 바로 로그아웃되지 않게 한 번 묻는다 */
export function LogoutModal({
  open,
  email,
  onClose,
}: {
  open: boolean;
  email: string;
  onClose: () => void;
}) {
  const { logout, pending, error } = useLogout();
  return (
    <Modal
      open={open}
      onClose={() => !pending && onClose()}
      labelledBy="account-title"
      // 하단 탭까지 덮어, 창이 떠 있는 동안 다른 화면으로 가지 않게 한다
      overlayClassName="fixed z-40"
      className="flex max-w-[520px] flex-col gap-6 px-[30px] pt-8 pb-6"
    >
      <div className="flex flex-col gap-2">
        <h2 id="account-title" className="font-display text-[30px] leading-[1.25] text-ink">
          로그아웃할까요?
        </h2>
        <p className="text-[17px] text-mute">{email}</p>
      </div>
      {error && <FieldError>{error}</FieldError>}
      <div className="flex gap-2.5">
        <button
          type="button"
          onClick={onClose}
          disabled={pending}
          className="flex h-[68px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[19px] font-bold text-ink"
        >
          취소
        </button>
        <PillButton variant="dark" className="h-[68px] flex-1" busy={pending} onClick={logout}>
          {pending ? "로그아웃 중" : "로그아웃"}
        </PillButton>
      </div>
    </Modal>
  );
}
