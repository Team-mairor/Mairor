"use client";

import { ChevronRight, Plus } from "lucide-react";
import { useEffect, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { MyHeader } from "@/features/my";
import {
  emptyDraft,
  POUCH_CATS,
  PouchBoard,
  PouchOpenFx,
  ProductSheet,
  type ProductDraft,
} from "@/features/pouch";
import { useSession } from "@/features/session";
import { useQuery } from "@/lib/hooks/use-query";
import { cn } from "@/lib/utils";

/** 마이페이지 · 내 파우치 (POUCH-004). ?add=1 로 등록 시트, ?edit=<id> 로 수정 시트를 바로 연다 */
export default function MyPouchPage() {
  const { state } = useSession();
  const query = useQuery();
  const [cat, setCat] = useState<string>("전체");
  const [form, setForm] = useState<ProductDraft | null>(null);
  // 진입 연출 2.2초
  const [fx, setFx] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setFx(false), 2200);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!query) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 요청을 한 번 반영한다
    if (query.get("add")) setForm(emptyDraft());
    const edit = query.get("edit");
    const item = edit && state.pouch.find((p) => p.id === edit);
    if (item) setForm({ ...item });
    if (query.get("demo") === "shade-fail")
      setForm(emptyDraft({ brand: "롬앤", name: "쥬시 래스팅 틴트", cat: "립" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 주소를 읽은 시점의 파우치만 본다
  }, [query]);

  const list = cat === "전체" ? state.pouch : state.pouch.filter((p) => p.cat === cat);
  const empty = state.pouch.length === 0 || query?.get("empty") === "1";

  return (
    <main className="relative flex min-h-0 flex-1 flex-col">
      {fx && <PouchOpenFx />}
      <MyHeader tab="pouch" />
      <div className="flex min-h-0 flex-1 flex-col gap-7 overflow-y-auto px-10 pt-1 pb-8">
        {empty ? (
          <div className="flex flex-col items-center gap-3.5 rounded-3xl border-[1.5px] border-dashed border-line-2 px-8 py-14 text-center">
            <span className="font-serif text-[34px] leading-none text-navy italic">
              Empty pouch
            </span>
            <span className="font-display text-[26px] text-ink">아직 등록한 제품이 없어요</span>
            <span className="text-[18px] leading-[1.55] text-pretty text-mute">
              가진 제품을 등록하면 영상 속 제품과 맞춰 보유·대체를 찾아 드려요.
            </span>
            <PillButton size="xl" onClick={() => setForm(emptyDraft())} className="mt-1.5">
              <Plus className="size-[18px]" strokeWidth={2.2} aria-hidden />
              제품 등록
            </PillButton>
          </div>
        ) : (
          <>
            <PouchBoard
              items={state.pouch}
              scale={0.66}
              className="h-[340px] shrink-0"
              onEdit={(p) => setForm({ ...p })}
            >
              <div className="absolute top-5 right-[22px] left-[22px] z-[2] flex items-start justify-between">
                <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
                  <span className="font-serif text-[32px] leading-none text-ink italic">
                    My pouch
                  </span>
                  <span className="text-[16px] text-mute">
                    내 파우치 · {state.pouch.length}개 · 탭해서 수정
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => setForm(emptyDraft())}
                  className="flex h-11 items-center gap-2 rounded-full bg-ink px-[18px] text-[17px] font-semibold text-white"
                >
                  <Plus className="size-4" strokeWidth={2} aria-hidden />
                  제품 추가
                </button>
              </div>
            </PouchBoard>

            <div className="flex flex-col gap-3.5">
              <div className="flex items-baseline gap-2.5">
                <span className="font-serif text-[26px] leading-none text-ink italic">
                  All items
                </span>
                <span className="text-[16px] text-mute">
                  {cat === "전체" ? "전체 제품" : cat} · {list.length}개
                </span>
              </div>
              <div className="flex flex-wrap gap-2" role="tablist" aria-label="카테고리">
                {["전체", ...POUCH_CATS].map((k) => {
                  const on = cat === k;
                  const n =
                    k === "전체"
                      ? state.pouch.length
                      : state.pouch.filter((p) => p.cat === k).length;
                  return (
                    <button
                      key={k}
                      type="button"
                      role="tab"
                      aria-selected={on}
                      onClick={() => setCat(k)}
                      className={cn(
                        "flex h-11 items-center gap-1.5 rounded-full border-[1.5px] px-[18px] text-[16px] font-bold transition-colors",
                        on
                          ? "border-navy bg-navy text-white"
                          : n
                            ? "border-line bg-white text-ink"
                            : "border-line bg-white text-ash",
                      )}
                    >
                      {k}
                      <span className="text-[14px] font-semibold tabular opacity-70">{n}</span>
                    </button>
                  );
                })}
              </div>
              <div className="grid grid-cols-2 gap-3">
                {list.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setForm({ ...p })}
                    className="flex min-w-0 items-center gap-3.5 rounded-[20px] border border-line bg-white py-3.5 pr-[18px] pl-3.5 text-left transition-colors hover:border-navy"
                  >
                    <span
                      className="size-14 shrink-0 rounded-full border-4 border-white shadow-float ring-1 ring-line"
                      style={{ background: p.color ?? "var(--color-cream)" }}
                    />
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="text-[14px] font-bold text-navy">
                        {p.cat} · <span className="font-medium text-mute">{p.brand}</span>
                      </span>
                      <span className="truncate font-serif text-[21px] leading-[1.15] text-ink">
                        {p.name}
                      </span>
                    </span>
                    <ChevronRight
                      className="size-[18px] shrink-0 text-ash"
                      strokeWidth={2}
                      aria-hidden
                    />
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {form && (
        <ProductSheet
          draft={form}
          onClose={() => setForm(null)}
          initialFail={query?.get("demo") === "shade-fail" && !form.id}
        />
      )}
    </main>
  );
}
