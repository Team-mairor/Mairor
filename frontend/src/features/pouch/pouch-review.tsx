import type { PouchItem } from "@/domain/pouch/catalog";

import { PouchBoard } from "./pouch-board";

/**
 * 파우치 확인 모달의 본문: 제목 두 줄 · 안내 · 파우치 보드.
 * 분석을 기다리는 동안(로딩)과 시작하기 전(제품 체크)이 같이 쓰고, 머리·버튼만 화면마다 다르다
 */
export function PouchReview({
  lead,
  desc,
  items,
  onEdit,
}: {
  /** 제목 첫 줄 (기다리는 동안 · 시작하기 전에) */
  lead: string;
  desc: string;
  items: PouchItem[];
  onEdit: (item: PouchItem) => void;
}) {
  return (
    <>
      <div className="flex flex-col gap-2">
        <span className="font-display text-[30px] leading-[1.3] text-ink">
          {lead}
          <br />내 파우치를 확인해 볼까요?
        </span>
        <span className="text-[19px] leading-[1.5] text-mute">{desc}</span>
      </div>
      <PouchBoard items={items} scale={0.6} className="h-[440px] shrink-0" onEdit={onEdit}>
        <div className="absolute top-5 left-[22px] z-[6]">
          <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
            <span className="font-serif text-[32px] leading-none text-ink italic">My pouch</span>
            <span className="text-[16px] text-mute">{items.length}개 · 탭해서 수정</span>
          </span>
        </div>
      </PouchBoard>
    </>
  );
}
