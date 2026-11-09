"use client";

import { ArrowDown, Check, Contrast, List, Plus, Smile } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import {
  GROUPS,
  GuideCheck,
  similarity,
  SwapPanel,
  TAG_BG,
  Toast,
  PouchModal,
  StartModal,
} from "@/features/check";
import { useHiddenVideo } from "@/features/face";
import { useRunQuery as useQuery } from "@/features/guide";
import { GlassPanel, LiveNote, LiveTag, RoundBack, useLiveState } from "@/features/live";
import { MakeupOverlay } from "@/features/overlay";
import { emptyDraft, ProductSheet, type PouchItem, type ProductDraft } from "@/features/pouch";
import {
  hasSame,
  matchCounts,
  matchFor,
  REF_STATE_LABEL,
  sameName,
  useSession,
  type Choice,
  type MatchKind,
  type RefProduct,
} from "@/features/session";
import { useTimeout } from "@/lib/hooks/use-timeout";
import { cn } from "@/lib/utils";
import { REF_PRODUCTS, TRY_STEPS } from "@/mocks/mock-data";

const DEFAULT_LAYERS = "/fixtures/layers/sample.json";

/** 08 제품 체크 */
export default function CheckPage() {
  const { state } = useSession();
  return state.run.mode === "guide" ? <GuideCheck /> : <SampleCheck />;
}

/** 샘플 제품 체크. ?view=try 로 입혀보기부터 연다 */
function SampleCheck() {
  const router = useRouter();
  const query = useQuery();
  const { state, updateRun } = useSession();
  const run = state.run;
  const pouch = state.pouch;
  // 비어 있는 파우치는 matchFor가 알아서 없음 처리한다. ?empty=1 은 빈 상태 확인용
  const emptyPouch = pouch.length === 0 || query?.get("empty") === "1";

  const [view, setView] = useState<"list" | "try">("list");
  const [group, setGroup] = useState<MatchKind | null>(null);
  const [focus, setFocus] = useState<number | null>(null);
  const [tryIdx, setTryIdx] = useState(0);
  const activeTab = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    activeTab.current?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [tryIdx, view]);
  const [swapFor, setSwapFor] = useState<number | null>(null);
  const [swapBack, setSwapBack] = useState(false);
  const [compare, setCompare] = useState(false);
  const [pouchModal, setPouchModal] = useState(false);
  const [form, setForm] = useState<ProductDraft | null>(null);
  const [skipAsk, setSkipAsk] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; text: string } | null>(null);
  const toastT = useTimeout();

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 보기를 한 번 반영한다
    if (query?.get("view") === "try") setView("try");
  }, [query]);

  const m = (i: number) => matchFor(REF_PRODUCTS[i], run, pouch, emptyPouch);
  const counts = matchCounts(REF_PRODUCTS, run, pouch, emptyPouch);
  const activeGroup = group ?? (counts.none ? "none" : counts.sub ? "sub" : "same");
  const items = REF_PRODUCTS.map((r, i) => ({ r, i, pr: m(i) }));
  const shown = items.filter((x) => x.pr.kind === activeGroup);
  const tryRef = TRY_STEPS[tryIdx];
  const cur = items[tryRef];

  /** null이면 선택을 지워 기본 매칭(보유 > 추천 대체)으로 돌아간다 */
  const setChoice = (id: string, v: Choice | null) =>
    updateRun((prev) => {
      const choice = { ...prev.choice };
      if (v == null) delete choice[id];
      else choice[id] = v;
      return { choice };
    });

  /** 같은 카테고리 파우치 제품을 색이 가까운 순으로 */
  const candidates = (r: RefProduct) =>
    (emptyPouch ? [] : pouch)
      .filter((p) => p.cat === r.matchCat && p.color)
      .map((p) => ({ p, s: similarity(r.color, p.color!) }))
      .sort((a, b) => b.s - a.s)
      .map((x) => x.p);

  const goTry = (i?: number) => {
    const t = i != null ? TRY_STEPS.indexOf(i as (typeof TRY_STEPS)[number]) : -1;
    setTryIdx(
      t >= 0
        ? t
        : Math.max(
            0,
            TRY_STEPS.findIndex((ri) => m(ri).kind !== "same"),
          ),
    );
    setSwapFor(null);
    setView("try");
  };
  const goList = (i?: number) => {
    const ri = i ?? tryRef;
    setFocus(ri);
    setGroup(m(ri).kind);
    setSwapFor(null);
    setView("list");
  };
  const closeSwap = () => {
    const back = swapBack;
    const ri = swapFor;
    setSwapFor(null);
    setSwapBack(false);
    if (back && ri != null) goTry(ri);
  };
  const start = () => setSkipAsk(true);
  const startTutorial = () => {
    setSkipAsk(false);
    // ?empty=1 로 확인한 결과를 run에 확정해, 튜토리얼이 실제 파우치로 다시 매칭하지 않게 한다
    if (emptyPouch)
      updateRun({
        choice: Object.fromEntries(REF_PRODUCTS.map((r) => [r.id, { kind: "none" } as Choice])),
      });
    router.push("/tutorial/guide");
  };
  const showToast = (ok: boolean, text: string) => {
    setToast({ ok, text });
    toastT.set(() => setToast(null), 2800);
  };
  // matchFor와 같은 기준(이름이 같을 때만 보유)으로 판단해야 안내와 목록이 어긋나지 않는다
  const onSaved = (item: PouchItem, isNew: boolean) => {
    if (!isNew) return;
    const hit = REF_PRODUCTS.find((rf) => sameName(item.name, rf.name));
    if (hit) {
      setChoice(hit.id, { kind: "pouch", id: item.id });
      setGroup("same");
      showToast(true, `'${hit.name}' 보유로 바꿨어요`);
    } else showToast(false, `'${item.name}' 추가 완료 · 영상 속 제품과는 달라요`);
  };

  const noneRows = items.filter((x) => x.pr.kind === "none");
  const layersUrl = query ? (query.get("layers") ?? DEFAULT_LAYERS) : null;
  // 카메라 오류·얼굴 없음이면 안내를 띄우고 메이크업은 숨긴다
  const { note, canRender, reason } = useLiveState();
  useHiddenVideo();

  return (
    <main className="relative flex flex-1 flex-col">
      {/* 누르고 있으면 영상 메이크업(원본), 아니면 내가 고른 제품 색. ponytail: 레이어는 같은 파일을 쓰고 전환만 한다 */}
      {/* 화장은 상단 탭과 하단 패널 사이 빈 칸에만 그린다 */}
      <div className="relative mt-[150px] flex-1">
        <MakeupOverlay layersUrl={layersUrl} hidden={!canRender} fit />
      </div>

      {/* 목록은 얼굴을 덮는 시트라 인식 안내가 필요 없고, 같은 자리(top 84px)라 제목줄을 가린다. 입혀볼 때만 띄운다.
          입혀볼 때는 84px에 부위 탭이 있어, 탭을 가리지 않게 화장 영역 시작(150px)으로 내린다 */}
      {view === "try" && <LiveNote note={note} className="top-[150px]" />}
      <div className="absolute inset-x-5 top-5 flex items-center justify-between gap-3">
        <LiveTag />
        <div className="min-w-0 flex-1" />
        {view === "try" && (
          <button
            type="button"
            onPointerDown={(e) => {
              e.currentTarget.setPointerCapture(e.pointerId);
              setCompare(true);
            }}
            onPointerUp={() => setCompare(false)}
            onPointerCancel={() => setCompare(false)}
            onPointerLeave={() => setCompare(false)}
            className={cn(
              "flex h-12 shrink-0 touch-none items-center gap-2.5 rounded-full border border-white/25 py-0 pr-[18px] pl-2 text-[16px] font-bold whitespace-nowrap select-none",
              compare ? "bg-blush text-ink" : "bg-night/80 text-white",
            )}
          >
            <span
              className={cn(
                "flex size-[34px] items-center justify-center rounded-full",
                compare ? "bg-night/15" : "bg-white/12",
              )}
            >
              <Contrast className="size-[18px]" strokeWidth={2} aria-hidden />
            </span>
            {compare ? "영상 메이크업 보는 중" : "누르고 있으면 영상과 비교"}
          </button>
        )}
        <button
          type="button"
          onClick={() => (view === "try" ? goList() : goTry())}
          className="flex h-12 shrink-0 items-center gap-2 rounded-full bg-white py-0 pr-5 pl-3.5 text-[16px] font-extrabold whitespace-nowrap text-ink shadow-float hover:bg-cream-3"
        >
          {view === "try" ? (
            <List className="size-5" strokeWidth={2.2} aria-hidden />
          ) : (
            <Smile className="size-5" strokeWidth={2} aria-hidden />
          )}
          {view === "try" ? "목록 보기" : "얼굴에 입혀보기"}
        </button>
      </div>

      {view === "try" && (
        <div className="absolute inset-x-5 top-[84px] flex justify-center">
          {/* 단계 수가 영상마다 달라, 넘치면 가로로 넘겨 보고 지금 탭이 보이게 맞춘다 */}
          <div className="flex max-w-full [scrollbar-width:none] gap-1.5 overflow-x-auto rounded-full border border-white/15 bg-night/80 p-[5px]">
            {TRY_STEPS.map((ri, k) => {
              const on = k === tryIdx;
              const pr = m(ri);
              return (
                <button
                  key={ri}
                  ref={on ? activeTab : undefined}
                  type="button"
                  onClick={() => setTryIdx(k)}
                  className={cn(
                    "flex h-11 shrink-0 items-center gap-2 rounded-full py-0 pr-4 pl-3 text-[16px] font-bold whitespace-nowrap transition-colors",
                    on ? "bg-white text-ink" : "text-line-2",
                  )}
                >
                  <span
                    className="size-[18px] shrink-0 rounded-full border-2"
                    style={{
                      background: pr.p?.color ?? "transparent",
                      borderColor: pr.p
                        ? on
                          ? "var(--color-ink)"
                          : "rgba(255,255,255,.4)"
                        : "var(--color-blush)",
                    }}
                  />
                  {REF_PRODUCTS[ri].cat}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {view === "list" ? (
        <GlassPanel
          className="inset-x-0 top-[84px] bottom-0 gap-[22px] rounded-t-[36px] rounded-b-none border-x-0 border-b-0 px-0 pt-[30px] pb-5"
          coversFace={false}
        >
          {swapFor != null && (
            <SwapPanel
              title={`${REF_PRODUCTS[swapFor].cat} 바꾸기`}
              refProduct={{
                name: `${REF_PRODUCTS[swapFor].brand} ${REF_PRODUCTS[swapFor].name}`,
                color: REF_PRODUCTS[swapFor].color,
              }}
              curId={m(swapFor).p?.id ?? null}
              skipped={m(swapFor).kind === "none"}
              ranked
              list={candidates(REF_PRODUCTS[swapFor])}
              onPick={(id) => {
                setChoice(REF_PRODUCTS[swapFor].id, id);
                closeSwap();
              }}
              onClose={closeSwap}
            />
          )}
          {toast && <Toast toast={toast} />}
          <div className="mb-2 flex items-end justify-between gap-4 border-b border-white/12 px-8 pb-[30px]">
            <div className="flex min-w-0 flex-col gap-1.5">
              <div className="flex items-baseline gap-3.5">
                <span className="shrink-0 font-serif text-[72px] leading-[.85] text-blush italic tabular">
                  {counts.same + counts.sub}
                  <span className="text-[40px] text-ash">/{REF_PRODUCTS.length}</span>
                </span>
                <h1 className="font-display text-[34px] leading-[1.15] text-white">
                  내 파우치와 맞춰봤어요
                </h1>
              </div>
              {emptyPouch && (
                <span className="text-[19px] leading-[1.5] text-blush">
                  파우치가 비어 있어 모두 &apos;없음&apos;이에요. 제품을 등록하면 다시 맞춰 봐요.
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setPouchModal(true)}
              className="flex h-[52px] shrink-0 items-center gap-2 rounded-full border border-white/25 px-5 text-[17px] font-bold whitespace-nowrap text-white"
            >
              <Plus className="size-[18px]" strokeWidth={2.6} aria-hidden />
              제품 등록
            </button>
          </div>

          <div
            className="mx-8 grid grid-cols-3 gap-1.5 rounded-[26px] border border-white/12 bg-white/8 p-1.5"
            role="tablist"
          >
            {GROUPS.map((g) => {
              const on = activeGroup === g.k;
              const n = counts[g.k];
              return (
                <button
                  key={g.k}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => setGroup(g.k)}
                  // 고른 탭은 그룹 색으로 채우고 체크를 붙인다. 흰 면은 미러필름 모드에서 검정이 되어 고른 티가 안 났다
                  className={cn(
                    "flex h-[76px] items-center gap-3 rounded-[20px] px-5 transition-[background,box-shadow]",
                    on ? cn(TAG_BG[g.k], "shadow-float") : "hover:bg-white/8",
                  )}
                >
                  {on ? (
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-ink text-[#fff]">
                      <Check className="size-4" strokeWidth={3.2} aria-hidden />
                    </span>
                  ) : (
                    <span
                      className="size-3.5 shrink-0 rounded-full"
                      style={{ background: g.dot }}
                    />
                  )}
                  <span
                    className={cn(
                      "min-w-0 flex-1 text-left text-[24px] font-extrabold",
                      on ? "text-ink" : "text-white",
                    )}
                  >
                    {g.label}
                  </span>
                  <span
                    className={cn(
                      "font-serif text-[48px] leading-none tabular",
                      on ? "text-ink" : "text-line-2",
                    )}
                  >
                    {n}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-8">
            {shown.length === 0 ? (
              <div className="py-10 text-center text-[20px] font-semibold text-ash">
                {GROUPS.find((g) => g.k === activeGroup)?.label} 제품이 없어요
              </div>
            ) : (
              shown.map(({ r, i, pr }) => {
                const canTry = TRY_STEPS.includes(i as (typeof TRY_STEPS)[number]);
                const Actions = (
                  <span className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setSwapFor(i);
                        setFocus(i);
                        setSwapBack(false);
                      }}
                      className="flex h-[60px] items-center rounded-full bg-cream-3 px-6 text-[19px] font-bold whitespace-nowrap text-ink hover:bg-line"
                    >
                      바꾸기
                    </button>
                    <button
                      type="button"
                      disabled={!canTry}
                      onClick={() => goTry(i)}
                      className={cn(
                        "flex h-[60px] items-center rounded-full px-6 text-[19px] font-bold whitespace-nowrap",
                        canTry ? "bg-ice text-ink hover:brightness-105" : "bg-cream-3 text-ash",
                      )}
                    >
                      미리보기
                    </button>
                  </span>
                );
                const Head = (
                  <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                    <span className="flex min-w-0 items-center gap-2">
                      <span
                        className={cn(
                          "flex h-[26px] shrink-0 items-center rounded-full px-2.5 text-[14px] font-extrabold text-ink",
                          TAG_BG[pr.kind],
                        )}
                      >
                        {GROUPS.find((g) => g.k === pr.kind)?.label}
                      </span>
                      <span className="truncate text-[18px] font-semibold text-mute">
                        {r.cat} · {r.brand}
                      </span>
                    </span>
                    <span className="truncate text-[28px] leading-[1.25] font-bold text-ink">
                      {r.name}
                    </span>
                    {pr.kind !== "sub" && pr.p && pr.kind !== "same" && (
                      <span className="truncate text-[19px] font-bold text-navy">
                        → {pr.p.brand} {pr.p.name}
                      </span>
                    )}
                  </span>
                );
                const outline =
                  focus === i ? "outline outline-[3px] -outline-offset-[3px] outline-blush" : "";
                return pr.kind === "sub" ? (
                  // 영상 속 제품 → 대신 쓸 내 제품을 위아래로 잇는다. 원본 보유 여부는 고른 제품과 따로 본다
                  <div
                    key={r.id}
                    className={cn(
                      "flex shrink-0 animate-fade flex-col overflow-hidden rounded-[28px] bg-white/90 text-ink shadow-float backdrop-blur-md mirror:shadow-[inset_0_0_0_2px_var(--color-line-2)]",
                      outline,
                    )}
                  >
                    <div className="flex items-center gap-5 px-6 pt-5 pb-6 pl-[26px]">
                      <span
                        className="size-16 shrink-0 rounded-full"
                        style={{ background: r.color }}
                      />
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="flex h-[26px] shrink-0 items-center rounded-full bg-ink px-2.5 text-[14px] font-extrabold text-white">
                            영상 속
                          </span>
                          <span className="truncate text-[17px] font-semibold text-mute">
                            {r.cat} · {r.brand}
                          </span>
                        </span>
                        <span className="truncate text-[24px] leading-[1.25] font-bold text-ink">
                          {r.name}
                        </span>
                        <span className="text-[15px] font-semibold text-mute">
                          {!emptyPouch && hasSame(r, pouch)
                            ? "내 파우치에 있음"
                            : "내 파우치에 없음"}
                        </span>
                      </span>
                    </div>
                    <div className="relative flex items-center gap-5 border-t border-line bg-mint-pale px-6 pt-6 pb-5 pl-[26px]">
                      <span className="absolute -top-[18px] left-[42px] flex size-9 items-center justify-center rounded-full border border-line bg-white text-ink">
                        <ArrowDown className="size-5" strokeWidth={2.6} aria-hidden />
                      </span>
                      <span
                        className="size-16 shrink-0 rounded-full ring-4 ring-mint"
                        style={{ background: pr.p?.color ?? "#fff" }}
                      />
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="flex min-w-0 items-center gap-2">
                          <span className="flex h-[26px] shrink-0 items-center gap-1 rounded-full bg-mint px-2.5 text-[14px] font-extrabold text-ink">
                            <Check className="size-3.5" strokeWidth={3.2} aria-hidden />
                            대체 제품
                          </span>
                          <span className="truncate text-[17px] font-semibold text-mute">
                            {pr.p?.brand}
                          </span>
                        </span>
                        <span className="truncate text-[24px] leading-[1.25] font-bold text-ink">
                          {pr.p?.name}
                        </span>
                      </span>
                      {Actions}
                    </div>
                  </div>
                ) : (
                  <div
                    key={r.id}
                    className={cn(
                      "flex min-h-[136px] shrink-0 animate-fade items-center gap-6 rounded-[28px] bg-white/90 px-6 py-6 pl-[26px] text-ink shadow-float backdrop-blur-md mirror:shadow-[inset_0_0_0_2px_var(--color-line-2)]",
                      outline,
                    )}
                  >
                    <span className="relative size-20 shrink-0">
                      <span
                        className="absolute inset-0 rounded-full"
                        style={{ background: r.color }}
                      />
                    </span>
                    {Head}
                    {Actions}
                  </div>
                );
              })
            )}
          </div>

          {/* 인식 안내는 목록에서 숨겨도, 카메라 오류와 재시도는 제목줄을 가리지 않게 버튼 위에 남긴다 */}
          {reason === "error" && (
            <LiveNote note={note} className="relative inset-x-auto top-auto mx-8 shrink-0" />
          )}
          <div className="flex shrink-0 items-center gap-2.5 px-8">
            <RoundBack onClick={() => router.push("/preview")} label="미리보기로" />
            <PillButton size="cta" trailing onClick={start} className="min-w-0 flex-1">
              이 조합으로 시작
            </PillButton>
          </div>
        </GlassPanel>
      ) : (
        <GlassPanel
          className="relative inset-x-0 bottom-0 gap-4 rounded-t-[36px] rounded-b-none border-x-0 border-b-0 px-0 pt-[22px] pb-[18px]"
          coversFace={false}
        >
          {toast && <Toast toast={toast} />}
          <div className="flex flex-col gap-1 px-7">
            <div className="flex min-w-0 items-baseline gap-3">
              <span className="shrink-0 font-serif text-[40px] leading-[.9] text-blush italic tabular">
                {tryIdx + 1}/{TRY_STEPS.length}
              </span>
              <span className="font-display text-[30px] leading-[1.15] whitespace-nowrap text-white">
                {cur.r.cat}
              </span>
              <span
                className="flex h-[30px] shrink-0 items-center self-center rounded-full px-3 text-[14px] font-bold"
                style={{
                  background: {
                    same: "color-mix(in srgb, var(--color-sky) 18%, transparent)",
                    sub: "color-mix(in srgb, var(--color-mint) 18%, transparent)",
                    none: "color-mix(in srgb, var(--color-blush) 16%, transparent)",
                  }[cur.pr.kind],
                  color: {
                    same: "var(--color-sky)",
                    sub: "var(--color-mint)",
                    none: "var(--color-blush)",
                  }[cur.pr.kind],
                }}
              >
                {GROUPS.find((g) => g.k === cur.pr.kind)?.label}
              </span>
            </div>
            <div className="mt-2 flex min-w-0 items-center gap-3.5 rounded-[20px] border border-white/15 bg-white/10 py-3 pr-[18px] pl-3">
              <span
                className="size-11 shrink-0 rounded-full border-[3px] border-white/40"
                style={{ background: cur.r.color }}
              />
              <span className="flex h-[30px] shrink-0 items-center rounded-full bg-white px-3 text-[15px] font-extrabold text-ink">
                영상 속
              </span>
              <span className="flex min-w-0 items-baseline gap-2">
                <span className="shrink-0 text-[18px] font-semibold whitespace-nowrap text-line-2">
                  {cur.r.brand}
                </span>
                <span className="min-w-0 truncate text-[22px] font-bold text-white">
                  {cur.r.name}
                </span>
              </span>
              {cur.r.refState && (
                <span className="ml-auto flex h-7 shrink-0 items-center rounded-full border-[1.5px] border-dashed border-blush px-2.5 text-[14px] font-bold whitespace-nowrap text-blush">
                  {REF_STATE_LABEL[cur.r.refState]}
                </span>
              )}
            </div>
            <span className="mt-2 text-[16px] leading-[1.5] text-ash">
              색은 영상에서 추정한 값이라 실제 발색과 다를 수 있어요
            </span>
          </div>

          <div className="flex gap-2.5 overflow-x-auto px-7 pb-0.5">
            {(() => {
              const r = cur.r;
              const ch = run.choice[r.id];
              const opts: {
                key: string;
                brand: string;
                label: string;
                color: string;
                match: string;
                rec: boolean;
                on: boolean;
                pick: () => void;
              }[] = [];
              const def = emptyPouch
                ? null
                : hasSame(r, pouch)
                  ? { p: r, tag: "영상과 같은 제품" }
                  : r.sub
                    ? { p: r.sub, tag: "추천 1" }
                    : null;
              if (def)
                opts.push({
                  key: "def",
                  brand: def.p.brand,
                  label: def.p.name,
                  color: def.p.color,
                  match: def.tag,
                  rec: true,
                  on: !ch,
                  pick: () => setChoice(r.id, null),
                });
              candidates(r)
                .filter((p) => !(def && p.name === def.p.name))
                .slice(0, 6)
                .forEach((p) => {
                  const rk = opts.length + 1;
                  opts.push({
                    key: p.id,
                    brand: p.brand,
                    label: p.name,
                    color: p.color!,
                    match: rk <= 3 ? `추천 ${rk}` : "같은 종류",
                    rec: rk <= 3,
                    on: ch?.kind === "pouch" && ch.id === p.id,
                    pick: () => setChoice(r.id, { kind: "pouch", id: p.id }),
                  });
                });
              return opts.map((o) => (
                <button
                  key={o.key}
                  type="button"
                  onClick={o.pick}
                  className={cn(
                    "flex w-[210px] shrink-0 items-center gap-3 rounded-[18px] border-2 py-3 pr-3.5 pl-3 text-left transition-colors",
                    o.on ? "border-blush bg-blush/16" : "border-white/10 bg-white/4",
                  )}
                >
                  <span
                    className="size-11 shrink-0 rounded-full border-2 border-white/30"
                    style={{ background: o.color }}
                  />
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span
                      className={cn(
                        "text-[13px] font-bold whitespace-nowrap",
                        o.rec ? "text-mint" : "text-ash",
                      )}
                    >
                      {o.match}
                    </span>
                    <span className="truncate text-[17px] leading-[1.25] font-bold text-white">
                      {o.label}
                    </span>
                    <span className="truncate text-[13px] font-semibold text-ash">{o.brand}</span>
                  </span>
                </button>
              ));
            })()}
            <button
              type="button"
              onClick={() => setChoice(cur.r.id, { kind: "none" })}
              className={cn(
                "flex shrink-0 items-center gap-2.5 rounded-[18px] border-2 border-dashed py-3 pr-[18px] pl-3",
                cur.pr.kind === "none" ? "border-blush bg-blush/16" : "border-white/20",
              )}
            >
              <span className="size-11 shrink-0 rounded-full border-2 border-dashed border-white/40" />
              <span className="text-[16px] font-bold whitespace-nowrap text-white">없이 진행</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setSwapFor(tryRef);
                setSwapBack(true);
                setFocus(tryRef);
                setGroup(cur.pr.kind);
                setView("list");
              }}
              className="flex shrink-0 items-center rounded-[18px] border-2 border-white/12 px-5 text-[16px] font-bold whitespace-nowrap text-blush"
            >
              전체 보기
            </button>
          </div>

          <div className="flex items-center gap-3 px-7">
            <RoundBack
              onClick={() => (tryIdx > 0 ? setTryIdx(tryIdx - 1) : goList())}
              label="이전 부위"
            />
            {tryIdx < TRY_STEPS.length - 1 && (
              <button
                type="button"
                onClick={() => setTryIdx(tryIdx + 1)}
                className="flex h-[72px] min-w-0 flex-1 items-center justify-center rounded-full border border-white/25 px-6 text-white hover:bg-white/14"
              >
                <span className="truncate text-[20px] font-bold">
                  다음 · {REF_PRODUCTS[TRY_STEPS[tryIdx + 1]].cat}
                </span>
              </button>
            )}
            <PillButton size="cta" onClick={start} className="min-w-0 flex-1">
              <span className="truncate">이 조합으로 시작</span>
            </PillButton>
          </div>
        </GlassPanel>
      )}

      <PouchModal
        open={pouchModal}
        pouch={pouch}
        onEdit={(p) => setForm({ ...p })}
        onAdd={() => setForm(emptyDraft())}
        onClose={() => setPouchModal(false)}
      />

      <StartModal
        open={skipAsk}
        missing={noneRows.map(({ r }) => ({
          key: r.id,
          label: `${r.brand} ${r.name}`,
          color: r.color,
        }))}
        onRecheck={() => {
          setSkipAsk(false);
          setGroup("none");
          setView("list");
        }}
        onStart={startTutorial}
        onClose={() => setSkipAsk(false)}
      />

      {form && <ProductSheet draft={form} onClose={() => setForm(null)} onSaved={onSaved} />}
    </main>
  );
}
