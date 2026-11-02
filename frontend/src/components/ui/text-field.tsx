import * as React from "react";

import { cn } from "@/lib/utils";

/** 60px 높이의 둥근 입력 칸. 오류면 테두리를 붉게 */
export function TextField({
  className,
  invalid = false,
  ...props
}: React.ComponentProps<"input"> & { invalid?: boolean }) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(
        "h-[60px] w-full min-w-0 rounded-2xl border bg-white px-[22px] text-[18px] text-ink outline-none placeholder:text-ash-3 focus:border-plum",
        invalid ? "border-wine-2" : "border-line-2",
        className,
      )}
      {...props}
    />
  );
}
