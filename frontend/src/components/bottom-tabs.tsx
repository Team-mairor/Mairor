"use client";

import { BarChart3, Home, PlaySquare, ShoppingBag } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/home", label: "홈", Icon: Home, match: (p: string) => p === "/home" },
  { href: "/select", label: "튜토리얼", Icon: PlaySquare, match: () => false },
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

/** 하단 탭 4개. 홈·마이페이지·리포트 상세에서만 보인다 */
export function BottomTabs({ hidden = false }: { hidden?: boolean }) {
  const pathname = usePathname();
  if (hidden) return null;
  return (
    <nav
      aria-label="주요 메뉴"
      className="grid h-32 shrink-0 grid-cols-4 gap-2 border-t border-line-2 bg-white px-8 pt-3 pb-5 shadow-[0_-8px_24px_rgba(11,20,48,.06)]"
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
                "flex h-12 w-[84px] items-center justify-center rounded-full transition-colors",
                on ? "bg-plum text-white" : "text-mute-2",
              )}
            >
              <Icon className="size-[30px]" strokeWidth={on ? 2 : 1.8} aria-hidden />
            </span>
            <span
              className={cn(
                "text-[20px] tracking-[-.01em]",
                on ? "font-bold text-plum" : "font-semibold text-mute-2",
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
