import * as React from "react";
import { ArrowRight } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

import { Spinner } from "./spinner";

// 프로토타입의 둥근 큰 버튼. 비활성은 연한 회색 배경(line-2)으로 눌리지 않는다.
// cta(72px)·hero(80px)는 화면 아래 큰 버튼 크기다. 주요 버튼은 primary, 옆의 보조 버튼은 line으로 쓴다.
// trailing을 주면 오른쪽에 화살표 원이 붙고 글씨는 왼쪽으로 붙는다.
const pillVariants = cva(
  "group inline-flex shrink-0 items-center justify-center gap-2.5 rounded-full font-semibold whitespace-nowrap transition-[background,transform] select-none outline-none focus-visible:ring-3 focus-visible:ring-ring/40 active:not-disabled:scale-[.99] disabled:cursor-default tabular",
  {
    variants: {
      variant: {
        primary: "bg-ice text-ink disabled:bg-line-2",
        navy: "bg-navy text-white disabled:bg-line-2",
        outline:
          "border border-ink text-ink hover:bg-cream-2 disabled:border-line-2 disabled:text-ash-2",
        soft: "bg-cream text-ink hover:bg-cream-3 disabled:text-ash-2",
        dark: "bg-ink text-white disabled:bg-line-2",
        white: "bg-white text-ink shadow-float disabled:text-ash-2",
        /** 큰 주요 버튼 옆의 보조 버튼 (나중에·다시 확인·다른 영상 등) */
        line: "border-2 border-line text-ink hover:bg-cream-2 disabled:text-ash-2",
      },
      size: {
        md: "h-[52px] px-6 text-[17px]",
        lg: "h-[60px] px-7 text-[19px]",
        xl: "h-16 px-8 text-[20px]",
        cta: "h-[72px] gap-3 px-[30px] text-[22px] font-bold active:not-disabled:scale-[.98]",
        hero: "h-20 gap-3 px-8 text-[23px] font-bold active:not-disabled:scale-[.97]",
      },
    },
    compoundVariants: [
      { variant: "primary", size: ["cta", "hero"], className: "shadow-cta disabled:shadow-none" },
    ],
    defaultVariants: { variant: "primary", size: "lg" },
  },
);

export function PillButton({
  className,
  variant,
  size,
  busy = false,
  asChild = false,
  trailing = false,
  children,
  disabled,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof pillVariants> &
  // asChild(Slot)는 자식이 하나여야 해서, 자식을 더하는 busy(스피너)·trailing(화살표 원)과 같이 쓸 수 없다
  (
    | {
        asChild?: false;
        /** 처리 중. 스피너를 보이고 중복 클릭을 막는다 */
        busy?: boolean;
        /** 오른쪽 화살표 원 */
        trailing?: boolean;
      }
    | { asChild: true; busy?: never; trailing?: never }
  )) {
  // Slot은 자식이 정확히 하나여야 해서, 스피너·화살표 자리 없이 children만 넘긴다
  if (asChild)
    return (
      <Slot.Root className={cn(pillVariants({ variant, size }), className)} {...props}>
        {children}
      </Slot.Root>
    );
  return (
    <button
      type="button"
      className={cn(
        pillVariants({ variant, size }),
        trailing && "justify-between gap-4 pr-2.5",
        className,
      )}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...props}
    >
      {busy && <Spinner className="size-[18px]" />}
      {trailing ? (
        <>
          <span className="min-w-0 truncate text-left">{children}</span>
          <span
            className={cn(
              // 비활성이면 원도 흐리게 해 눌릴 것처럼 보이지 않게 한다
              "flex shrink-0 items-center justify-center rounded-full bg-ink text-ice group-disabled:bg-white group-disabled:text-line-3",
              size === "hero" ? "size-[60px]" : "size-[54px]",
            )}
          >
            <ArrowRight
              className={size === "hero" ? "size-7" : "size-[26px]"}
              strokeWidth={2.4}
              aria-hidden
            />
          </span>
        </>
      ) : (
        children
      )}
    </button>
  );
}

export { pillVariants };
