"use client";

import { useEffect, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * 화면 위 덮개와 카드. onClose를 주면 배경을 탭하거나 Esc를 눌러 닫힌다. 안 주면 닫는 길은 안쪽 버튼뿐이다.
 * 덮개 색·카드 면·그림자는 여기에만 둔다. 화면마다 다른 z 순서·여백은 overlayClassName, 카드 모양은 className으로 준다.
 * ponytail: 포커스 트랩 없음. 접근성 검수(S15P31A306-116)에서 필요하면 radix Dialog로 바꾼다.
 */
export function Modal({
  open,
  onClose,
  children,
  className,
  overlayClassName,
  align = "center",
  labelledBy,
  label,
}: {
  open: boolean;
  onClose?: () => void;
  children: ReactNode;
  className?: string;
  overlayClassName?: string;
  /** bottom: 아래에서 올라오는 시트 */
  align?: "center" | "bottom";
  labelledBy?: string;
  label?: string;
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
        "absolute inset-0 z-20 flex justify-center bg-night/55",
        align === "center" ? "items-center p-6" : "items-end",
        overlayClassName,
      )}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={label}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-full bg-white shadow-modal",
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
