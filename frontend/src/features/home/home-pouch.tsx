"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import type { PouchItem } from "@/domain/pouch";
import type { PouchSync } from "@/domain/session";
import { PouchBoard } from "@/features/pouch";

const MIN_POUCH_STICKER_HEIGHT = 260;

/** 홈의 파우치 보드. 서버 목록을 받는 중·실패·빈 상태를 보드 위에 안내한다 */
export function HomePouch({
  pouch,
  sync,
  waiting,
  hidden,
  compact,
}: {
  pouch: PouchItem[];
  sync: { status: PouchSync; retry: () => void };
  waiting: boolean;
  hidden: boolean;
  /** 위 카드가 길어 보드가 낮아졌을 때 스티커를 숨겨 겹치지 않게 한다 */
  compact: boolean;
}) {
  const router = useRouter();
  const boardRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  const hideStickers = compact && height > 0 && height < MIN_POUCH_STICKER_HEIGHT;

  useEffect(() => {
    const board = boardRef.current;
    if (!board) return;

    const update = () => setHeight(board.getBoundingClientRect().height);
    update();

    const observer = new ResizeObserver(update);
    observer.observe(board);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={boardRef} className="min-h-0 flex-1">
      <PouchBoard
        items={hideStickers ? [] : pouch}
        scale={0.6}
        className="h-full"
        onEdit={(p) => router.push(`/my/pouch?edit=${p.id}`)}
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
                내 파우치 · {pouch.length}개 · 탭해서 수정
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
        {pouch.length === 0 && !hidden && (
          <div className="absolute inset-0 z-[1] flex flex-col items-center justify-center gap-3.5 px-10 pt-[90px] pb-6 text-center">
            <span className="font-display text-[24px] leading-[1.35] text-ink">
              파우치가 비어 있어요
            </span>
            <span className="max-w-[420px] text-[17px] leading-[1.5] text-pretty text-mute">
              가진 제품을 담아 두면 영상 속 제품과 비교해 바로 쓸 수 있는 것과 대체할 수 있는 것을
              알려 드려요.
            </span>
            <Link
              href="/my/pouch?add=1"
              className="flex h-12 items-center gap-2 rounded-full bg-ice px-[22px] text-[17px] font-semibold text-ink"
            >
              <Plus className="size-4" strokeWidth={2} aria-hidden />첫 제품 담기
            </Link>
          </div>
        )}
      </PouchBoard>
    </div>
  );
}
