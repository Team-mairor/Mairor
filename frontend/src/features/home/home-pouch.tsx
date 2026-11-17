"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import type { PouchItem } from "@/domain/pouch";
import type { PouchSync } from "@/domain/session";
import { EXAMPLE_POUCH, PouchBoard } from "@/features/pouch";

/**
 * 홈의 파우치 보드. 서버 목록을 받는 중·실패는 머리말로 알리고, 비었으면 예시 스티커를 흐리게 보여 준다.
 * 위 카드가 많아도 스티커가 머리말과 겹치지 않는 높이(260px)는 남기고, 모자라면 홈이 스크롤된다
 */
export function HomePouch({
  pouch,
  sync,
  waiting,
  hidden,
}: {
  pouch: PouchItem[];
  sync: { status: PouchSync; retry: () => void };
  waiting: boolean;
  hidden: boolean;
}) {
  const router = useRouter();
  // 비었으면 예시 스티커를 흐리게 보여 준다(누르면 제품 등록, 파우치에 넣지 않는다)
  const shown = pouch.length === 0 && !hidden ? EXAMPLE_POUCH : null;

  return (
    <div data-tour="home-pouch" className="min-h-[260px] flex-1">
      <PouchBoard
        items={shown ?? pouch}
        dim={Boolean(shown)}
        scale={0.6}
        className="h-full"
        onEdit={(p) => router.push(shown ? "/my/pouch?add=1" : `/my/pouch?edit=${p.id}`)}
        stickerSize="lg"
      >
        <div className="absolute top-5 right-[22px] left-[22px] z-[2] flex items-start justify-between">
          <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
            <span className="font-serif text-[32px] leading-none text-ink italic">My pouch</span>
            {sync.status === "error" ? (
              <span className="flex items-center gap-2 text-[16px] text-mute">
                파우치를 불러오지 못했어요
                <button type="button" onClick={sync.retry} className="font-bold text-navy">
                  다시 시도
                </button>
              </span>
            ) : waiting ? (
              <span className="text-[16px] text-mute">파우치를 불러오고 있어요</span>
            ) : (
              <span className="text-[16px] text-mute">
                {shown
                  ? "예시 · 제품을 담으면 내 파우치로 바뀌어요"
                  : `내 파우치 · ${pouch.length}개 · 탭해서 수정`}
              </span>
            )}
          </span>
          <Link
            href="/my/pouch?add=1"
            className="flex h-11 items-center gap-2 rounded-full bg-ink px-[18px] text-[17px] font-semibold text-white"
          >
            <Plus className="size-4" strokeWidth={2} aria-hidden />
            제품 추가
          </Link>
        </div>
      </PouchBoard>
    </div>
  );
}
