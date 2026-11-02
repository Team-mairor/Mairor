import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

import { Spinner } from "./spinner";

// 프로토타입의 둥근 큰 버튼. 비활성은 연한 회색 배경(line-2)으로 눌리지 않는다.
const pillVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2.5 rounded-full font-semibold whitespace-nowrap transition-[background,transform] select-none outline-none focus-visible:ring-3 focus-visible:ring-ring/40 active:not-disabled:scale-[.99] disabled:cursor-default tabular",
  {
    variants: {
      variant: {
        primary: "bg-pink text-white disabled:bg-line-2",
        plum: "bg-plum text-white disabled:bg-line-2",
        outline:
          "border border-ink text-ink hover:bg-cream-2 disabled:border-line-2 disabled:text-ash-2",
        soft: "bg-cream text-ink hover:bg-cream-3 disabled:text-ash-2",
        dark: "bg-ink text-white disabled:bg-line-2",
        white: "bg-white text-ink shadow-[0_8px_24px_rgba(11,20,48,.12)] disabled:text-ash-2",
      },
      size: {
        md: "h-[52px] px-6 text-[17px]",
        lg: "h-[60px] px-7 text-[19px]",
        xl: "h-16 px-8 text-[20px]",
      },
    },
    defaultVariants: { variant: "primary", size: "lg" },
  },
);

export function PillButton({
  className,
  variant,
  size,
  busy = false,
  asChild = false,
  children,
  disabled,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof pillVariants> & {
    /** 처리 중. 스피너를 보이고 중복 클릭을 막는다 */
    busy?: boolean;
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      type={asChild ? undefined : "button"}
      className={cn(pillVariants({ variant, size }), className)}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...props}
    >
      {busy && <Spinner className="size-[18px]" />}
      {children}
    </Comp>
  );
}

export { pillVariants };
