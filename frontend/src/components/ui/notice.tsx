import { AlertCircle, Check, Clock } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const TONES = {
  success: { box: "bg-mint-pale", icon: "text-mint-ink", Icon: Check },
  info: { box: "bg-cream", icon: "text-mute", Icon: AlertCircle },
  error: { box: "bg-ice-tint", icon: "text-error", Icon: AlertCircle },
  expired: { box: "bg-cream", icon: "text-navy", Icon: Clock },
  locked: { box: "bg-ice-tint", icon: "text-navy", Icon: Clock },
} as const;

/** 화면 안 안내 상자. 한 줄이면 가로, 설명이 있으면 세로로 쌓는다 */
export function Notice({
  tone = "info",
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof TONES;
  title?: ReactNode;
  children?: ReactNode;
  /** 오른쪽 또는 아래 링크 버튼 */
  action?: ReactNode;
  className?: string;
}) {
  const { box, icon, Icon } = TONES[tone];
  const stacked = !!title && !!children;
  return (
    <div
      role={tone === "error" || tone === "locked" ? "alert" : "status"}
      className={cn(
        "flex gap-2.5 rounded-[14px] px-4 py-3 text-[16px] leading-[1.5] text-ink",
        stacked ? "flex-col gap-1 py-3.5" : "items-center",
        box,
        className,
      )}
    >
      <span className={cn("flex items-center gap-2.5", stacked && "font-bold")}>
        <Icon className={cn("size-[18px] shrink-0", icon)} strokeWidth={2.2} aria-hidden />
        {title ?? children}
      </span>
      {stacked && <span className="pl-7 text-mute">{children}</span>}
      {action && (
        <span className={cn("font-bold text-navy", stacked ? "pl-7" : "ml-auto")}>{action}</span>
      )}
    </div>
  );
}

/** 입력 칸 아래 한 줄 오류 */
export function FieldError({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2 text-[16px] text-error", className)} role="alert">
      <AlertCircle className="size-[18px] shrink-0" strokeWidth={2} aria-hidden />
      {children}
    </span>
  );
}
