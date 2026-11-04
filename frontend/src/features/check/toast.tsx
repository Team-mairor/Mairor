"use client";

import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export function Toast({ toast }: { toast: { ok: boolean; text: string } }) {
  return (
    <div
      role="status"
      className={cn(
        "absolute top-0 left-5 flex h-[60px] max-w-[calc(100%-40px)] -translate-y-[calc(100%+12px)] animate-fade items-center gap-3 rounded-full py-0 pr-5 pl-2.5 shadow-float",
        toast.ok ? "bg-ink text-white" : "bg-white/92 text-ink",
      )}
    >
      <span
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-full text-ink",
          toast.ok ? "bg-sky" : "bg-ash",
        )}
      >
        <Check className="size-[18px]" strokeWidth={2.6} aria-hidden />
      </span>
      <span className="truncate text-[15px] font-bold">{toast.text}</span>
    </div>
  );
}
