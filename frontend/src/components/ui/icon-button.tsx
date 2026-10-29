import * as React from "react";
import { ChevronLeft, X } from "lucide-react";

import { cn } from "@/lib/utils";

/** 동그란 아이콘 버튼. 기본은 뒤로 가기 */
export function IconButton({
  className,
  icon = "back",
  size = 60,
  children,
  ...props
}: React.ComponentProps<"button"> & { icon?: "back" | "close" | "none"; size?: 44 | 60 }) {
  const Icon = icon === "back" ? ChevronLeft : icon === "close" ? X : null;
  return (
    <button
      type="button"
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full border text-ink hover:bg-cream-2 disabled:opacity-40",
        size === 60 ? "size-[60px] border-ink" : "size-11 border-line",
        className,
      )}
      {...props}
    >
      {Icon && (
        <Icon className={size === 60 ? "size-[22px]" : "size-5"} strokeWidth={1.9} aria-hidden />
      )}
      {children}
    </button>
  );
}
