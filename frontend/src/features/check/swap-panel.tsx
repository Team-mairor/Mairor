"use client";

import { ArrowLeft } from "lucide-react";
import { useState } from "react";

import { toneOf } from "@/domain/check";
import type { PouchItem } from "@/domain/pouch";
import type { Choice } from "@/domain/session";
import { cn } from "@/lib/utils";

/** 바꾸기 패널. ranked면 상위 3개에 추천을 표시한다 */
export function SwapPanel({
  title,
  refProduct,
  list,
  curId,
  skipped,
  ranked,
  emptyText = "파우치에 같은 종류 제품이 없어요",
  onPick,
  onClear,
  onClose,
}: {
  title: string;
  refProduct: { name: string; color: string | null };
  list: PouchItem[];
  curId: string | null;
  skipped: boolean;
  ranked: boolean;
  emptyText?: string;
  onPick: (choice: Choice) => void;
  /** 있으면 선택 해제 버튼을 보여 준다 */
  onClear?: () => void;
  onClose: () => void;
}) {
  const [tone, setTone] = useState("전체");
  const colored = list.filter((p) => p.color);
  const tones = ["전체", ...new Set(colored.map((p) => toneOf(p.color!)))];
  const shown = tone === "전체" ? list : colored.filter((p) => toneOf(p.color!) === tone);
  return (
    <div className="absolute inset-0 z-[3] flex animate-slide-in flex-col gap-5 rounded-[36px] bg-night pt-[26px] pb-5">
      <div className="flex items-center gap-4 px-8">
        <button
          type="button"
          onClick={onClose}
          aria-label="닫기"
          className="flex size-14 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/8 text-white hover:bg-white/15"
        >
          <ArrowLeft className="size-6" strokeWidth={2.2} aria-hidden />
        </button>
        <h2 className="font-display text-[38px] leading-[1.15] text-white">{title}</h2>
      </div>
      <div className="mx-8 flex items-center gap-4 rounded-[20px] border border-white/10 bg-white/5 px-[18px] py-3.5">
        <span
          className={cn(
            "size-14 shrink-0 rounded-full",
            refProduct.color
              ? "border-[3px] border-white/30"
              : "border-[2.5px] border-dashed border-white/40",
          )}
          style={refProduct.color ? { background: refProduct.color } : undefined}
        />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[17px] font-semibold text-line-2">영상 속 제품</span>
          <span className="truncate text-[24px] font-bold text-white">{refProduct.name}</span>
        </span>
        {ranked && (
          <span className="text-[17px] font-semibold whitespace-nowrap text-line-2">
            비슷한 색 순
          </span>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-8">
        <span className="flex items-baseline justify-between gap-3">
          <span className="text-[22px] font-extrabold text-white">내 파우치에서 고르기</span>
          <span className="text-[17px] font-semibold whitespace-nowrap text-ash">
            {!list.length
              ? ""
              : ranked
                ? `추천 상위 ${Math.min(3, list.length)}개 · 색 기준 통과 ${list.length}개`
                : `고를 수 있는 제품 ${list.length}개`}
          </span>
        </span>
        {list.length === 0 && (
          <span className="py-7 text-center text-[20px] font-semibold text-ash">{emptyText}</span>
        )}
        {colored.length > 9 && (
          <div className="flex flex-wrap gap-2">
            {tones.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setTone(t)}
                aria-pressed={t === tone}
                className={cn(
                  "flex h-11 items-center rounded-full px-[18px] text-[17px] font-semibold",
                  t === tone ? "bg-white text-ink" : "bg-white/10 text-white",
                )}
              >
                {t}
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3.5">
          {shown.map((p, i) => {
            const on = curId === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onPick({ kind: "pouch", id: p.id })}
                className={cn(
                  "flex min-w-0 items-center gap-[18px] rounded-3xl border-2 py-[18px] pr-[18px] pl-4 text-left transition-colors hover:bg-white/10",
                  on ? "border-blush bg-blush/14" : "border-white/10 bg-white/5",
                )}
              >
                <span
                  className={cn(
                    "size-[76px] shrink-0 rounded-full",
                    p.color
                      ? "border-[3px] border-white/30"
                      : "border-[2.5px] border-dashed border-white/40",
                  )}
                  style={p.color ? { background: p.color } : undefined}
                />
                <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <span className="flex min-h-[30px] items-center gap-2">
                    {ranked && i < 3 && (
                      <span className="text-[22px] font-extrabold whitespace-nowrap text-mint">
                        추천 {i + 1}
                      </span>
                    )}
                    {on && (
                      <span className="flex h-[30px] items-center rounded-full bg-blush px-3 text-[15px] font-extrabold text-ink">
                        선택됨
                      </span>
                    )}
                  </span>
                  <span className="truncate text-[17px] font-semibold text-line-2">
                    {p.cat} · {p.brand}
                  </span>
                  <span className="line-clamp-2 text-[23px] leading-[1.25] font-bold text-white">
                    {p.name}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2.5 px-8">
        <button
          type="button"
          onClick={() => onPick({ kind: "none" })}
          className={cn(
            "flex h-[72px] flex-1 items-center justify-center rounded-full border-2 border-dashed text-[21px] font-bold text-white hover:bg-white/12",
            skipped ? "border-blush" : "border-white/30",
          )}
        >
          제품 생략
        </button>
        {onClear && (
          <button
            type="button"
            onClick={onClear}
            className="flex h-[72px] flex-1 items-center justify-center rounded-full border-2 border-white/30 text-[21px] font-bold text-white hover:bg-white/12"
          >
            선택 해제
          </button>
        )}
        <button
          type="button"
          onClick={onClose}
          className="flex h-[72px] flex-1 items-center justify-center rounded-full bg-white text-[21px] font-bold text-ink"
        >
          지금 선택 유지
        </button>
      </div>
    </div>
  );
}
