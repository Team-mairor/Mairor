"use client";

import { ArrowLeft } from "lucide-react";
import { useState } from "react";

import type { PouchItem } from "@/features/pouch";
import type { Choice, MatchKind, RefProduct } from "@/features/session";
import { cn } from "@/lib/utils";

import { toneOf } from "./color";

/** 바꾸기 패널: 같은 카테고리 파우치 제품, 색이 가까운 상위 3개에 추천 표시 */
export function SwapPanel({
  r,
  cur,
  list,
  onPick,
  onClose,
}: {
  r: RefProduct;
  cur: { kind: MatchKind; p: { brand: string; name: string } | null };
  list: PouchItem[];
  onPick: (choice: Choice) => void;
  onClose: () => void;
}) {
  const curId = (cur.p as PouchItem | null)?.id;
  const [tone, setTone] = useState("전체");
  const tones = ["전체", ...new Set(list.map((p) => toneOf(p.color ?? "#FFFFFF")))];
  const shown = tone === "전체" ? list : list.filter((p) => toneOf(p.color ?? "#FFFFFF") === tone);
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
        <h2 className="font-display text-[38px] leading-[1.15] text-white">{r.cat} 바꾸기</h2>
      </div>
      <div className="mx-8 flex items-center gap-4 rounded-[20px] border border-white/10 bg-white/5 px-[18px] py-3.5">
        <span
          className="size-14 shrink-0 rounded-full border-[3px] border-white/30"
          style={{ background: r.color }}
        />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[17px] font-semibold text-line-2">영상 속 제품</span>
          <span className="truncate text-[24px] font-bold text-white">
            {r.brand} {r.name}
          </span>
        </span>
        <span className="text-[17px] font-semibold whitespace-nowrap text-line-2">
          비슷한 색 순
        </span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-8">
        <span className="flex items-baseline justify-between gap-3">
          <span className="text-[22px] font-extrabold text-white">내 파우치에서 고르기</span>
          <span className="text-[17px] font-semibold whitespace-nowrap text-ash">
            {list.length ? `추천 ${Math.min(3, list.length)}개 · 같은 종류 ${list.length}개` : ""}
          </span>
        </span>
        {list.length === 0 && (
          <span className="py-7 text-center text-[20px] font-semibold text-ash">
            파우치에 같은 종류 제품이 없어요
          </span>
        )}
        {list.length > 9 && (
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
                  className="size-[76px] shrink-0 rounded-full border-[3px] border-white/30"
                  style={{ background: p.color ?? "#fff" }}
                />
                <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <span className="flex min-h-[30px] items-center gap-2">
                    {i < 3 && (
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
            cur.kind === "none" ? "border-blush" : "border-white/30",
          )}
        >
          이 제품 없이 진행
        </button>
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
