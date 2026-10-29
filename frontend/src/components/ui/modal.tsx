"use client";

import { useEffect, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * 화면 가운데 카드. 배경을 탭하거나 Esc를 누르면 onClose.
 * ponytail: 포커스 트랩 없음. 접근성 검수(S15P31A306-116)에서 필요하면 radix Dialog로 바꾼다.
 */
export function Modal({
  open,
  onClose,
  children,
  className,
  align = "center",
  labelledBy,
}: {
  open: boolean;
  onClose?: () => void;
  children: ReactNode;
  className?: string;
  /** bottom: 아래에서 올라오는 시트 */
  align?: "center" | "bottom";
  labelledBy?: string;
}) {
  useEffect(() => {
    if (!open || !onClose) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className={cn(
        "absolute inset-0 z-20 flex justify-center bg-[rgba(40,10,26,.5)]",
        align === "center" ? "items-center p-6" : "items-end",
      )}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-full bg-white shadow-[0_30px_60px_rgba(20,4,12,.3)]",
          align === "center"
            ? "max-w-[560px] animate-fade rounded-[28px] p-7 pb-6"
            : "animate-sheet-up rounded-t-[28px] px-8 pt-6 pb-8",
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
}
