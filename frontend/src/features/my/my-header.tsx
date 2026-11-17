"use client";

import Link from "next/link";

import { useReports } from "@/domain/report";
import { displayName, useAuth, useMyPouch, useSessionActions } from "@/domain/session";
import { cn } from "@/lib/utils";

/** 마이페이지 상단: 프로필 + 내 파우치 · 리포트 탭. 로그아웃·미러필름 전환은 홈 상단에 있다 */
export function MyHeader({ tab }: { tab: "pouch" | "reports" }) {
  const { loggedIn, email, nickname } = useAuth();
  const { pouch } = useMyPouch();
  const { sessionChecked } = useSessionActions();
  // 로그인했으면 서버 목록 수(받은 만큼, 더 있으면 +)
  const reports = useReports(sessionChecked && loggedIn ? email : null);
  const reportCount = !loggedIn
    ? "0"
    : reports.load.status === "ready"
      ? `${reports.load.data.items.length}${reports.load.data.hasNext ? "+" : ""}`
      : "";

  const tabs = [
    {
      key: "pouch",
      href: "/my/pouch",
      en: "My pouch",
      ko: `파우치 ${loggedIn ? pouch.length : 0}`,
    },
    { key: "reports", href: "/my/reports", en: "Reports", ko: `리포트 ${reportCount}`.trim() },
  ] as const;
  const name = displayName({ nickname, email });
  const initial = (name.trim()[0] ?? "m").toUpperCase();
  return (
    <>
      <div className="flex shrink-0 items-center gap-[18px] px-10 pt-7">
        <span className="flex size-[72px] shrink-0 items-center justify-center rounded-full bg-mint font-serif text-[36px] text-ink italic">
          {initial}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="font-label text-[14px] font-semibold tracking-[.16em] text-navy">
            MY BEAUTY ARCHIVE
          </span>
          <h1 className="font-display text-[30px] leading-[1.2] text-ink">
            {name ? `${name}의 파우치와 룩` : "내 파우치와 룩"}
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
                    on ? "text-navy" : "text-ash",
                  )}
                >
                  {t.ko}
                </span>
                <span
                  className={cn(
                    "absolute right-[24%] -bottom-px left-[24%] h-[3px] rounded-full transition-colors",
                    on ? "bg-cyan" : "bg-transparent",
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
