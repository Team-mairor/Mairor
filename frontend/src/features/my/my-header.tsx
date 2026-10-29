"use client";

import Link from "next/link";

import { useSession } from "@/features/session";
import { cn } from "@/lib/utils";

/** 마이페이지 상단: 프로필 + 내 파우치 · 리포트 탭 */
export function MyHeader({ tab }: { tab: "pouch" | "reports" }) {
  const { state } = useSession();
  const tabs = [
    { key: "pouch", href: "/my/pouch", en: "My pouch", ko: `파우치 ${state.pouch.length}` },
    { key: "reports", href: "/my/reports", en: "Reports", ko: `리포트 ${state.reports.length}` },
  ] as const;
  const initial = (state.email.trim()[0] ?? "m").toUpperCase();
  return (
    <>
      <div className="flex shrink-0 items-center gap-[18px] px-10 pt-7">
        <span className="flex size-[72px] shrink-0 items-center justify-center rounded-full bg-lime font-serif text-[36px] text-ink italic">
          {initial}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="font-label text-[14px] font-semibold tracking-[.16em] text-plum">
            MY BEAUTY ARCHIVE
          </span>
          <h1 className="font-display text-[30px] leading-[1.2] text-ink">
            {state.email ? `${state.email.split("@")[0]}의 파우치와 룩` : "내 파우치와 룩"}
          </h1>
        </div>
      </div>
      <nav className="shrink-0 px-10 pt-9 pb-5" aria-label="마이페이지 탭">
        <div className="grid grid-cols-2 border-b border-line">
          {tabs.map((t) => {
            const on = tab === t.key;
            return (
              <Link
                key={t.key}
                href={t.href}
                aria-current={on ? "page" : undefined}
                className="relative flex h-16 items-center justify-center gap-2.5"
              >
                <span
                  className={cn(
                    "font-serif text-[30px] leading-none italic transition-colors",
                    on ? "text-ink" : "text-ash",
                  )}
                >
                  {t.en}
                </span>
                <span
                  className={cn(
                    "text-[16px] font-semibold whitespace-nowrap transition-colors",
                    on ? "text-plum" : "text-ash",
                  )}
                >
                  {t.ko}
                </span>
                <span
                  className={cn(
                    "absolute right-[24%] -bottom-px left-[24%] h-[3px] rounded-full transition-colors",
                    on ? "bg-pink" : "bg-transparent",
                  )}
                />
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
