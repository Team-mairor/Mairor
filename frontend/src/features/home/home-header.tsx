"use client";

import { LogOut } from "lucide-react";
import { useState } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { displayName, useAuth } from "@/domain/session";

import { LogoutModal } from "./logout-modal";

/** 홈 상단 로고와 미러필름 전환·로그아웃 메뉴 */
export function HomeHeader() {
  const { email, nickname } = useAuth();
  const [menu, setMenu] = useState(false);
  const [account, setAccount] = useState(false);

  return (
    <>
      <header className="flex h-[68px] shrink-0 items-center gap-3 px-8">
        <span className="font-serif text-[40px] leading-none tracking-[-.02em] text-navy italic">
          mairor
        </span>
        <div className="ml-auto flex items-center gap-3">
          <div data-tour="home-mirror" className="flex">
            <MirrorToggle fitFirst />
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setMenu((v) => !v)}
              className="flex size-11 items-center justify-center rounded-full bg-mint font-serif text-[22px] text-ink italic"
              aria-label="내 메뉴"
              aria-expanded={menu}
            >
              {(displayName({ nickname, email }).trim()[0] ?? "m").toUpperCase()}
            </button>
            {menu && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setMenu(false)} aria-hidden />
                <div className="absolute top-14 right-0 z-40 flex w-[200px] animate-fade flex-col rounded-3xl border border-line-2 bg-white p-3 shadow-modal">
                  <button
                    type="button"
                    onClick={() => {
                      setMenu(false);
                      setAccount(true);
                    }}
                    className="flex h-12 items-center justify-between rounded-2xl px-3 text-[17px] font-semibold text-error hover:bg-cream"
                  >
                    로그아웃
                    <LogOut className="size-5" aria-hidden />
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>
      <LogoutModal open={account} email={email} onClose={() => setAccount(false)} />
    </>
  );
}
