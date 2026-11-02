"use client";

import { ArrowLeft, ArrowRight, Check, Contrast, List, Plus, Smile } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { useHiddenVideo } from "@/features/face";
import {
  GlassPanel,
  LiveNote,
  LiveTag,
  RoundBack,
  useLiveState,
} from "@/features/live/live-chrome";
import { MakeupOverlay } from "@/features/overlay";
import { emptyDraft, PouchBoard, ProductSheet, type ProductDraft } from "@/features/pouch";
import {
  hasSame,
  matchCounts,
  matchFor,
  sameName,
  useSession,
  type Choice,
  type MatchKind,
} from "@/features/session";
import {
  REF_PRODUCTS,
  REF_STATE_LABEL,
  TRY_STEPS,
  type PouchItem,
  type RefProduct,
} from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const DEFAULT_LAYERS = "/fixtures/layers/sample.json";

const GROUPS: { k: MatchKind; label: string; dot: string }[] = [
  { k: "same", label: "보유", dot: "var(--color-sky)" },
  { k: "sub", label: "대체", dot: "var(--color-lime)" },
  { k: "none", label: "없음", dot: "var(--color-rose)" },
];
const TAG_BG: Record<MatchKind, string> = { same: "bg-sky", sub: "bg-lime", none: "bg-rose" };

function hex(c: string) {
  return [1, 3, 5].map((k) => parseInt(c.slice(k, k + 2), 16));
}
/** 색 거리 기반 유사도 (정렬용·화면 미노출) */
function similarity(a: string, b: string) {
  const x = hex(a);
  const y = hex(b);
  return 100 - Math.sqrt(x.reduce((t, v, i) => t + (v - y[i]) ** 2, 0)) / 4.4;
}

/**
 * 08 제품 체크 ↔ 입혀보며 고르기 (GUIDE-001 · GUIDE-004 · RECOMMEND-001/002).
 * 한 화면의 두 보기. 선택값은 세션 run.choice에 공유된다. ?view=try 로 입혀보기부터 연다.
 */
export default function CheckPage() {
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
  const toastT = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 보기를 한 번 반영한다
    if (query?.get("view") === "try") setView("try");
  }, [query]);
  useEffect(() => () => void (toastT.current && clearTimeout(toastT.current)), []);

  const m = (i: number) => matchFor(i, run, pouch, emptyPouch);
  const counts = matchCounts(run, pouch, emptyPouch);
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
    if (toastT.current) clearTimeout(toastT.current);
    toastT.current = setTimeout(() => setToast(null), 2800);
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
  // 카메라 오류·얼굴 없음이면 안내를 띄우고 메이크업은 숨긴다 (CAMERA-004)
  const { note, canRender } = useLiveState();
  useHiddenVideo();

  return (
    <main className="relative flex flex-1 flex-col">
      {/* 누르고 있으면 영상 메이크업(원본), 아니면 내가 고른 제품 색. ponytail: 레이어는 같은 파일을 쓰고 전환만 한다 */}
      {/* 화장은 상단 탭과 하단 패널 사이 빈 칸에만 그린다 */}
      <div className="relative mt-[150px] flex-1">
        <MakeupOverlay layersUrl={layersUrl} hidden={!canRender} fit />
      </div>

      <LiveNote note={note} />
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
              compare ? "bg-rose text-ink-deep" : "bg-[rgba(11,20,48,.82)] text-white",
            )}
          >
            <span
              className={cn(
                "flex size-[34px] items-center justify-center rounded-full",
                compare ? "bg-ink-deep/15" : "bg-white/12",
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
          className="flex h-12 shrink-0 items-center gap-2 rounded-full bg-white py-0 pr-5 pl-3.5 text-[16px] font-extrabold whitespace-nowrap text-ink shadow-[0_6px_16px_rgba(4,7,18,.25)] hover:bg-cream-3"
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
          <div className="flex max-w-full [scrollbar-width:none] gap-1.5 overflow-x-auto rounded-full border border-white/15 bg-[rgba(11,20,48,.78)] p-[5px]">
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
                        : "var(--color-rose)",
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
              r={REF_PRODUCTS[swapFor]}
              cur={m(swapFor)}
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
                <span className="shrink-0 font-serif text-[72px] leading-[.85] text-rose italic tabular">
                  {counts.same + counts.sub}
                  <span className="text-[40px] text-ash">/{REF_PRODUCTS.length}</span>
                </span>
                <h1 className="font-display text-[34px] leading-[1.15] text-white">
                  내 파우치와 맞춰봤어요
                </h1>
              </div>
              {emptyPouch && (
                <span className="text-[19px] leading-[1.5] text-rose">
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
                  className={cn(
                    "flex h-[76px] items-center gap-3 rounded-[20px] px-5 transition-[background,box-shadow]",
                    on ? "bg-white shadow-[0_6px_16px_rgba(4,7,18,.25)]" : "",
                  )}
                >
                  <span className="size-3.5 shrink-0 rounded-full" style={{ background: g.dot }} />
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
                      on ? "text-pink-deep" : "text-line-2",
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
                        canTry ? "bg-pink text-white hover:brightness-105" : "bg-cream-3 text-ash",
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
                      <span className="truncate text-[19px] font-bold text-plum">
                        → {pr.p.brand} {pr.p.name}
                      </span>
                    )}
                  </span>
                );
                const outline =
                  focus === i ? "outline outline-[3px] -outline-offset-[3px] outline-rose" : "";
                return pr.kind === "sub" ? (
                  <div
                    key={r.id}
                    className={cn(
                      "flex animate-fade flex-col overflow-hidden rounded-[28px] bg-white/90 text-ink shadow-[0_6px_20px_rgba(4,7,18,.18)] backdrop-blur-md",
                      outline,
                    )}
                  >
                    <div className="flex items-center gap-6 px-6 pt-6 pb-5 pl-[26px]">
                      <span
                        className="size-20 shrink-0 rounded-full"
                        style={{ background: r.color }}
                      />
                      {Head}
                    </div>
                    <div className="flex items-center gap-6 border-t border-line px-6 pt-5 pb-[22px] pl-[26px]">
                      <span className="flex w-20 shrink-0 justify-center text-plum">
                        <ArrowRight className="size-[26px]" strokeWidth={2.2} aria-hidden />
                      </span>
                      <span
                        className="size-12 shrink-0 rounded-full"
                        style={{ background: pr.p?.color ?? "#fff" }}
                      />
                      <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                        <span className="flex h-7 items-center self-start rounded-full bg-pink-tint px-3 text-[15px] font-extrabold whitespace-nowrap text-plum">
                          대체 제품
                        </span>
                        <span className="truncate text-[24px] leading-[1.25] font-bold text-ink">
                          {pr.p?.brand} {pr.p?.name}
                        </span>
                      </span>
                      {Actions}
                    </div>
                  </div>
                ) : (
                  <div
                    key={r.id}
                    className={cn(
                      "flex min-h-[136px] animate-fade items-center gap-6 rounded-[28px] bg-white/90 px-6 py-6 pl-[26px] text-ink shadow-[0_6px_20px_rgba(4,7,18,.18)] backdrop-blur-md",
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

          <div className="flex shrink-0 items-center gap-2.5 px-8">
            <RoundBack onClick={() => router.push("/preview")} label="미리보기로" />
            <button
              type="button"
              onClick={start}
              className="flex h-[72px] min-w-0 flex-1 items-center justify-between gap-4 rounded-full bg-pink py-0 pr-2.5 pl-[30px] text-white shadow-[0_12px_28px_color-mix(in_srgb,var(--color-pink)_38%,transparent)] active:scale-[.98]"
            >
              <span className="truncate text-[22px] font-bold">이 조합으로 시작</span>
              <span className="flex size-[54px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                <ArrowRight className="size-[26px]" strokeWidth={2.4} aria-hidden />
              </span>
            </button>
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
              <span className="shrink-0 font-serif text-[40px] leading-[.9] text-rose italic tabular">
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
                    sub: "color-mix(in srgb, var(--color-lime) 18%, transparent)",
                    none: "color-mix(in srgb, var(--color-rose) 16%, transparent)",
                  }[cur.pr.kind],
                  color: {
                    same: "var(--color-sky)",
                    sub: "var(--color-lime)",
                    none: "var(--color-rose)",
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
                <span className="ml-auto flex h-7 shrink-0 items-center rounded-full border-[1.5px] border-dashed border-rose px-2.5 text-[14px] font-bold whitespace-nowrap text-rose">
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
                    o.on ? "border-rose bg-rose/16" : "border-white/10 bg-white/4",
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
                        o.rec ? "text-lime" : "text-ash",
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
                cur.pr.kind === "none" ? "border-rose bg-rose/16" : "border-white/20",
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
              className="flex shrink-0 items-center rounded-[18px] border-2 border-white/12 px-5 text-[16px] font-bold whitespace-nowrap text-rose"
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
            <button
              type="button"
              onClick={start}
              className="flex h-[72px] min-w-0 flex-1 items-center justify-center rounded-full bg-pink px-6 text-white shadow-[0_12px_28px_color-mix(in_srgb,var(--color-pink)_38%,transparent)] active:scale-[.98]"
            >
              <span className="truncate text-[22px] font-bold">이 조합으로 시작</span>
            </button>
          </div>
        </GlassPanel>
      )}

      {/* 파우치 확인 모달 */}
      {pouchModal && (
        <div
          className="absolute inset-0 z-[8] flex items-center justify-center bg-[rgba(8,13,34,.62)] p-8"
          role="dialog"
          aria-modal="true"
          aria-label="내 파우치"
        >
          <div className="flex w-full flex-col gap-[22px] rounded-[28px] bg-white p-8 text-ink">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2.5 rounded-full bg-cream px-[18px] py-2.5 text-[17px] font-semibold">
                <span className="size-2 rounded-full bg-pink-deep" />내 파우치 · {pouch.length}개
              </span>
              <button
                type="button"
                onClick={() => setPouchModal(false)}
                aria-label="닫기"
                className="flex size-11 items-center justify-center rounded-full border border-line"
              >
                <ArrowLeft className="size-[18px]" strokeWidth={1.8} aria-hidden />
              </button>
            </div>
            <div className="flex flex-col gap-2">
              <span className="font-display text-[30px] leading-[1.3]">
                시작하기 전에
                <br />내 파우치를 확인해 볼까요?
              </span>
              <span className="text-[19px] leading-[1.5] text-mute">
                최근에 산 제품이 있다면 지금 등록해 두세요. 매칭에 바로 반영돼요.
              </span>
            </div>
            <PouchBoard
              items={pouch}
              scale={0.6}
              className="h-[440px] shrink-0"
              onEdit={(p) => setForm({ ...p })}
            >
              <div className="absolute top-5 left-[22px] z-[2]">
                <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
                  <span className="font-serif text-[32px] leading-none italic">My pouch</span>
                  <span className="text-[16px] text-mute">{pouch.length}개 · 탭해서 수정</span>
                </span>
              </div>
            </PouchBoard>
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={() => setForm(emptyDraft())}
                className="flex h-20 shrink-0 items-center gap-2 rounded-full border-2 border-line px-[30px] text-[21px] font-bold whitespace-nowrap active:scale-[.96]"
              >
                <Plus className="size-[18px]" strokeWidth={2} aria-hidden />새 제품 등록
              </button>
              <button
                type="button"
                onClick={() => setPouchModal(false)}
                className="ml-auto flex h-20 min-w-[300px] items-center justify-between gap-6 rounded-full bg-pink py-0 pr-2.5 pl-8 text-white shadow-[0_14px_30px_color-mix(in_srgb,var(--color-pink)_26%,transparent)] active:scale-[.97]"
              >
                <span className="truncate text-[23px] font-bold">다 했어요</span>
                <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                  <ArrowRight className="size-7" strokeWidth={2.4} aria-hidden />
                </span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 시작 확인 */}
      <Modal
        open={skipAsk}
        onClose={() => setSkipAsk(false)}
        className="flex max-w-none flex-col gap-7 rounded-[32px] px-9 pt-10 pb-8 text-ink"
      >
        <div className="flex flex-col gap-3">
          <h2 className="font-display text-[36px] leading-[1.25]">
            {noneRows.length ? `없는 제품 ${noneRows.length}개는` : "이대로"}
            <br />
            {noneRows.length ? "건너뛰고 시작할까요?" : "시작할까요?"}
          </h2>
          <p className="text-[20px] leading-[1.5] text-mute">
            {noneRows.length ? "이 단계들은 설명만 보여 드리고 넘어가요. " : ""}시작하면 제품을 바꿀
            수 없어요.
          </p>
        </div>
        {noneRows.length > 0 && (
          <div className="flex flex-col gap-2.5">
            {noneRows.map(({ r }) => (
              <div
                key={r.id}
                className="flex items-center gap-4 rounded-[22px] border-2 border-dashed border-ash px-5 py-4"
              >
                <span className="size-12 shrink-0 rounded-full" style={{ background: r.color }} />
                <span className="min-w-0 flex-1 truncate text-[22px] font-bold">
                  {r.brand} {r.name}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => {
              setSkipAsk(false);
              setGroup("none");
              setView("list");
            }}
            className="flex h-20 shrink-0 items-center justify-center rounded-full border-2 border-line px-[30px] text-[21px] font-bold whitespace-nowrap active:scale-[.96]"
          >
            다시 확인
          </button>
          <button
            type="button"
            onClick={startTutorial}
            className="ml-auto flex h-20 min-w-[300px] items-center justify-between gap-6 rounded-full bg-pink py-0 pr-2.5 pl-8 text-white shadow-[0_14px_30px_color-mix(in_srgb,var(--color-pink)_26%,transparent)] active:scale-[.97]"
          >
            <span className="truncate text-[23px] font-bold">
              {noneRows.length ? "건너뛰고 시작" : "시작하기"}
            </span>
            <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
              <ArrowRight className="size-7" strokeWidth={2.4} aria-hidden />
            </span>
          </button>
        </div>
      </Modal>

      {form && <ProductSheet draft={form} onClose={() => setForm(null)} onSaved={onSaved} />}
    </main>
  );
}

function Toast({ toast }: { toast: { ok: boolean; text: string } }) {
  return (
    <div
      role="status"
      className={cn(
        "absolute top-0 left-5 flex h-[60px] max-w-[calc(100%-40px)] -translate-y-[calc(100%+12px)] animate-fade items-center gap-3 rounded-full py-0 pr-5 pl-2.5 shadow-[0_10px_24px_rgba(6,10,26,.28)]",
        toast.ok ? "bg-ink text-white" : "bg-white/92 text-ink",
      )}
    >
      <span
        className={cn(
          "flex size-10 shrink-0 items-center justify-center rounded-full text-ink",
          toast.ok ? "bg-sky" : "bg-ash",
        )}
      >
        <Check className="size-[18px]" strokeWidth={2.6} aria-hidden />
      </span>
      <span className="truncate text-[15px] font-bold">{toast.text}</span>
    </div>
  );
}

/** 바꾸기 패널: 같은 카테고리 파우치 제품, 색이 가까운 상위 3개에 추천 표시 */
/** 색 계열 분류 (바꾸기 패널 톤 필터) */
function toneOf(c: string) {
  const [r, g, b] = hex(c);
  return r - b > 70 && g < r * 0.62
    ? "코랄·레드"
    : r - g < 45
      ? "로즈"
      : (r + g + b) / 3 > 190
        ? "누드"
        : "브라운";
}

function SwapPanel({
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
    <div className="absolute inset-0 z-[3] flex animate-slide-in flex-col gap-5 rounded-[36px] bg-ink-deep pt-[26px] pb-5">
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
                  on ? "border-rose bg-rose/14" : "border-white/10 bg-white/5",
                )}
              >
                <span
                  className="size-[76px] shrink-0 rounded-full border-[3px] border-white/30"
                  style={{ background: p.color ?? "#fff" }}
                />
                <span className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <span className="flex min-h-[30px] items-center gap-2">
                    {i < 3 && (
                      <span className="text-[22px] font-extrabold whitespace-nowrap text-lime">
                        추천 {i + 1}
                      </span>
                    )}
                    {on && (
                      <span className="flex h-[30px] items-center rounded-full bg-rose px-3 text-[15px] font-extrabold text-ink-deep">
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
            cur.kind === "none" ? "border-rose" : "border-white/30",
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
