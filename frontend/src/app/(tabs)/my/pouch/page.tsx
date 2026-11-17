"use client";

import { ChevronRight, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { CoachTour, type TourStep } from "@/components/coach-tour";
import { Notice } from "@/components/ui/notice";
import { emptyDraft, fromApi, getPouchItem, POUCH_CATS, type ProductDraft } from "@/domain/pouch";
import { usePouchSync } from "@/domain/session";
import { useAuth, useMyPouch, useSessionActions, useTour } from "@/domain/session";
import { MyHeader } from "@/features/my";
import { EXAMPLE_POUCH, PouchBoard, PouchOpenFx, ProductSheet } from "@/features/pouch";
import { shouldPlayPouchOpenFx } from "@/features/pouch/pouch-open-policy";
import { ApiError, errorMessage, isAbortError } from "@/lib/api";
import { useQuery } from "@/lib/hooks/use-query";
import { cn } from "@/lib/utils";

const TOUR: TourStep[] = [
  {
    target: "pouch-board",
    title: "파우치 보드",
    body: "최근 담은 제품이 스티커로 붙어요.\n스티커를 누르면 제품 정보를 고칠 수 있어요.",
  },
  {
    target: "pouch-add",
    title: "제품 등록",
    body: "카테고리와 종류를 고르고 브랜드·제품명·호수를 넣어요.\n색상 정보가 있어야 대체 후보로 추천돼요.",
  },
  {
    target: "pouch-cats",
    title: "카테고리별 목록",
    body: "카테고리별로 모아 보고, 목록에서 제품을 눌러 고치거나 파우치에서 뺄 수 있어요.",
  },
];

/** 마이페이지 · 내 파우치. ?add=1 등록, ?edit=<id> 수정 시트 */
export default function MyPouchPage() {
  const { loggedIn } = useAuth();
  const { pouch } = useMyPouch();
  const { sessionChecked, expireSession } = useSessionActions();
  const router = useRouter();
  const sync = usePouchSync();
  const query = useQuery();
  const [cat, setCat] = useState<string>("전체");
  const [form, setForm] = useState<ProductDraft | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // 진입 연출 2.2초. 같은 탭에서 최근에 봤다면 목록을 바로 보여 준다.
  const [fx, setFx] = useState(true);
  // 효과가 두 번 실행돼도(StrictMode) 재생 여부는 처음 한 번만 정한다
  const playFx = useRef<boolean | null>(null);
  useLayoutEffect(() => {
    playFx.current ??= shouldPlayPouchOpenFx(sessionStorage);
    if (!playFx.current) {
      setFx(false);
      return;
    }
    const t = setTimeout(() => setFx(false), 2200);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!query || !sessionChecked) return;
    if (query.get("add")) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 등록 요청을 한 번 반영한다
      if (loggedIn) setForm(emptyDraft());
      else router.replace("/login");
    }
  }, [query, router, sessionChecked, loggedIn]);

  // ?edit=<id>: 로그인했으면 서버의 최신 항목(API-POUCH-005)으로, 아니면 저장된 파우치에서 연다
  const edit = query?.get("edit") ?? null;
  useEffect(() => {
    if (!edit || !sessionChecked) return;
    if (!loggedIn) {
      const item = loggedIn ? pouch.find((p) => p.id === edit) : undefined;
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 요청을 한 번 반영한다
      if (item) setForm({ ...item });
      else if (!loggedIn) router.replace("/login");
      return;
    }
    const controller = new AbortController();
    getPouchItem(edit, controller.signal).then(
      (item) => setForm({ ...fromApi(item) }),
      (e: unknown) => {
        if (isAbortError(e)) return;
        if (e instanceof ApiError && e.code === "UNAUTHORIZED") {
          expireSession();
          router.replace("/login?expired=basic");
        } else if (e instanceof ApiError && e.code === "NOT_FOUND")
          setNotice("제품을 찾지 못했어요. 이미 지워졌을 수 있어요.");
        else setNotice(errorMessage(e));
      },
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 주소·로그인 상태가 정해질 때 한 번만 연다
  }, [edit, sessionChecked, loggedIn]);

  const pouchItems = loggedIn ? pouch : [];
  const list = cat === "전체" ? pouchItems : pouchItems.filter((p) => p.cat === cat);
  // 로그인했으면 서버 목록을 받기 전까지 저장된(지난) 파우치를 보여 주지 않는다
  const waiting = sync.status === "loading" || (loggedIn && !sessionChecked);
  const empty = pouchItems.length === 0 || query?.get("empty") === "1";
  // 진입 연출이 끝나고 목록을 받은 뒤에 안내한다
  const tour = useTour("pouch", !fx && !waiting && sync.status !== "error");

  // 목록에서 다시 고르면 지난 안내를 지운다
  const open = (d: ProductDraft) => {
    setNotice(null);
    setForm(d);
  };
  const add = () => (loggedIn ? open(emptyDraft()) : router.push("/login"));

  return (
    <main className="relative flex min-h-0 flex-1 flex-col">
      {fx && <PouchOpenFx />}
      <MyHeader tab="pouch" />
      <div className="scrollbar-hidden flex min-h-0 flex-1 flex-col gap-7 overflow-y-auto px-10 pt-1 pb-8">
        {notice && (
          <Notice tone="error" title={notice}>
            목록에서 다시 골라 주세요.
          </Notice>
        )}
        {sync.status === "error" ? (
          <div className="flex items-center justify-between gap-4 rounded-[20px] border border-line px-6 py-7">
            <span className="text-[17px] leading-[1.5] text-mute">
              파우치를 불러오지 못했어요. {errorMessage(sync.error)}
            </span>
            <button
              type="button"
              onClick={sync.retry}
              className="shrink-0 text-[17px] font-bold text-navy"
            >
              다시 시도
            </button>
          </div>
        ) : waiting ? (
          <span className="py-10 text-center text-[18px] text-mute">파우치를 불러오고 있어요</span>
        ) : (
          <>
            {/* 비어 있으면 같은 보드에 예시 스티커를 흐리게 보여 준다. 누르면 새 제품 등록 (파우치에 넣지 않는다) */}
            <div data-tour="pouch-board" className="shrink-0">
              <PouchBoard
                items={empty ? EXAMPLE_POUCH : pouchItems}
                dim={empty}
                scale={0.66}
                className="h-[340px]"
                onEdit={(p) => (empty ? add() : open({ ...p }))}
              >
                <div className="absolute top-5 right-[22px] left-[22px] z-[2] flex items-start justify-between">
                  <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
                    <span className="font-serif text-[32px] leading-none text-ink italic">
                      My pouch
                    </span>
                    <span className="text-[16px] text-mute">
                      {empty
                        ? "예시 · 제품을 등록하면 내 파우치로 바뀌어요"
                        : `내 파우치 · ${pouchItems.length}개 · 탭해서 수정`}
                    </span>
                  </span>
                  <button
                    type="button"
                    data-tour="pouch-add"
                    onClick={add}
                    className="flex h-11 items-center gap-2 rounded-full bg-ink px-[18px] text-[17px] font-semibold text-white"
                  >
                    <Plus className="size-4" strokeWidth={2} aria-hidden />
                    {empty ? "제품 등록" : "제품 추가"}
                  </button>
                </div>
              </PouchBoard>
            </div>

            {!empty && (
              <div className="flex flex-col gap-3.5">
                <div className="flex items-baseline gap-2.5">
                  <span className="font-serif text-[26px] leading-none text-ink italic">
                    All items
                  </span>
                  <span className="text-[16px] text-mute">
                    {cat === "전체" ? "전체 제품" : cat} · {list.length}개
                  </span>
                </div>
                <div
                  className="flex flex-wrap gap-2"
                  role="tablist"
                  aria-label="카테고리"
                  data-tour="pouch-cats"
                >
                  {["전체", ...POUCH_CATS].map((k) => {
                    const on = cat === k;
                    const n =
                      k === "전체"
                        ? pouchItems.length
                        : pouchItems.filter((p) => p.cat === k).length;
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
                        {/* 투명도로 흐리게 하면 미러필름 모드에서 안 보여서, 고른 칩만 투명도를 쓰고 나머지는 색으로 낮춘다 */}
                        <span
                          className={cn(
                            "text-[14px] font-semibold tabular",
                            on ? "opacity-70" : n ? "text-mute" : "",
                          )}
                        >
                          {n}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  {list.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => open({ ...p })}
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
            )}
          </>
        )}
      </div>

      {form && <ProductSheet draft={form} onClose={() => setForm(null)} />}
      {tour.show && !form && <CoachTour steps={TOUR} onDone={tour.done} />}
    </main>
  );
}
