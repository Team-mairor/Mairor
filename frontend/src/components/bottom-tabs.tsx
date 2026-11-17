"use client";

import { BarChart3, Camera, Home, PlaySquare, ShoppingBag } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/home", label: "홈", Icon: Home, match: (p: string) => p === "/home" },
  { href: "/photo", label: "오늘네컷", Icon: Camera, match: (p: string) => p.startsWith("/photo") },
  {
    href: "/select",
    label: "튜토리얼",
    Icon: PlaySquare,
    match: (p: string) => p.startsWith("/select"),
  },
  {
    href: "/my/pouch",
    label: "파우치",
    Icon: ShoppingBag,
    match: (p: string) => p.startsWith("/my/pouch"),
  },
  {
    href: "/my/reports",
    label: "리포트",
    Icon: BarChart3,
    match: (p: string) => p.startsWith("/my/report"),
  },
] as const;

/** 하단 탭 5개. (tabs) 화면에서 보인다 */
export function BottomTabs({
  hidden = false,
  force = false,
}: {
  hidden?: boolean;
  /** 경로와 상관없이 보인다. 오늘네컷 QR 화면처럼 화면 안에서 직접 넣을 때 쓴다 */
  force?: boolean;
}) {
  const pathname = usePathname();
  // 오늘네컷 촬영·완성 화면은 화면 전체를 쓴다
  if (hidden || (!force && pathname.startsWith("/photo/"))) return null;
  return (
    <nav
      aria-label="주요 메뉴"
      className="sticky inset-x-0 bottom-0 z-20 grid h-32 shrink-0 grid-cols-5 gap-1 border-t border-line-2 bg-white px-4 pt-3 pb-5 shadow-[0_-8px_24px_color-mix(in_srgb,var(--color-night)_6%,transparent)]"
    >
      {TABS.map(({ href, label, Icon, match }) => {
        const on = match(pathname);
        return (
          <Link
            key={href}
            href={href}
            aria-current={on ? "page" : undefined}
            className="flex flex-col items-center justify-center gap-2 transition-transform active:scale-[.96]"
          >
            <span
              className={cn(
                "flex h-12 w-14 items-center justify-center rounded-full transition-colors",
                on ? "bg-navy text-white" : "text-mute-2",
              )}
            >
              <Icon className="size-[30px]" strokeWidth={on ? 2 : 1.8} aria-hidden />
            </span>
            <span
              className={cn(
                "text-[16px] tracking-[-.01em]",
                on ? "font-bold text-navy" : "font-semibold text-mute-2",
              )}
            >
              {label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
