"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { Notice } from "@/components/ui/notice";
import { displayName, useSession } from "@/features/session";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useRequest } from "@/lib/hooks/use-request";
import { cn } from "@/lib/utils";

/** 마이페이지 상단: 프로필 · 로그아웃 + 내 파우치 · 리포트 탭 */
export function MyHeader({ tab }: { tab: "pouch" | "reports" }) {
  const router = useRouter();
  const { state, signOut } = useSession();
  const { pending, run } = useRequest<"logout">();
  const [logoutErr, setLogoutErr] = useState<string | null>(null);

  const loggedOut = () => {
    signOut();
    router.replace("/login");
  };

  /** API-USERS-003 */
  const logout = () => {
    setLogoutErr(null);
    return run(
      "logout",
      async (signal) => {
        await api.post("/v1/users/logout", { signal });
        loggedOut();
      },
      (e) => {
        // 세션이 이미 끝났으면(401) 로그아웃된 것으로 본다
        if (e instanceof ApiError && e.code === "UNAUTHORIZED") return loggedOut();
        setLogoutErr(errorMessage(e));
      },
    );
  };

  const tabs = [
    { key: "pouch", href: "/my/pouch", en: "My pouch", ko: `파우치 ${state.pouch.length}` },
    { key: "reports", href: "/my/reports", en: "Reports", ko: `리포트 ${state.reports.length}` },
  ] as const;
  const name = displayName(state);
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
        <div className="flex shrink-0 flex-col items-end gap-3 self-start">
          <MirrorToggle />
          <button
            type="button"
            onClick={logout}
            disabled={!!pending}
            className="text-[16px] text-mute underline disabled:text-ash-2"
          >
            {pending ? "로그아웃 중" : "로그아웃"}
          </button>
        </div>
      </div>
      {logoutErr && (
        <Notice tone="error" className="mx-10 mt-4">
          {logoutErr}
        </Notice>
      )}
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
