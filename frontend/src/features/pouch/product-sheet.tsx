"use client";

import { Check, ChevronDown, Pencil, Search } from "lucide-react";
import { useState } from "react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { useSession } from "@/features/session";
import { cn } from "@/lib/utils";

import {
  NO_SHADE_CATS,
  POUCH_CATS,
  POUCH_TYPES,
  SHADE_COLORS,
  type PouchCat,
  type PouchItem,
} from "./catalog";
import { Illustration, typeOf } from "./illustration";

/** 샘플 호수 목록 (API-POUCH-001: 브랜드·제품명으로 특정한 제품의 호수). */
const SHADES: Record<string, [string, string][]> = {
  베이스: [
    ["13N 포슬린", "#F3D9C4"],
    ["17C 바닐라", "#EDCDB2"],
    ["21N 린넨", "#E6C2A2"],
    ["21C 아이보리", "#E9C5AA"],
    ["23N 진저", "#DBB08D"],
    ["25N 탠", "#CFA07C"],
  ],
  아이: [
    ["01 코튼 브라운", "#C9A08A"],
    ["03 로지 모브", "#B8676E"],
    ["05 코코아", "#8A5A48"],
    ["07 버건디", "#7A2E3A"],
    ["09 샴페인", "#E8C9A8"],
  ],
  치크: [
    ["01 피치", "#F4A98A"],
    ["02 코랄", "#EF8E8A"],
    ["03 로즈", "#F2899B"],
    ["04 모브", "#C98A9C"],
  ],
  립: [
    ["01 누드 로즈", "#D08A86"],
    ["03 로지", "#C8235F"],
    ["05 칠리", "#B8352A"],
    ["07 플럼", "#8E2F4A"],
    ["09 코랄", "#E8665A"],
  ],
  브로우: [
    ["01 라이트 브라운", "#9A7358"],
    ["02 내추럴 브라운", "#6E4E3A"],
    ["03 다크 브라운", "#4A3428"],
    ["04 그레이 브라운", "#6B6058"],
  ],
  네일: [
    ["01 누드 핑크", "#E8B4B8"],
    ["03 코랄", "#EF8E8A"],
    ["05 레드", "#B3261E"],
    ["07 버건디", "#7A2E3A"],
    ["09 화이트", "#FFFFFF"],
  ],
};

export type ProductDraft = Omit<PouchItem, "id"> & { id?: string; custom?: boolean };

function Label({ children }: { children: React.ReactNode }) {
  return <span className="text-[15px] font-bold text-mute">{children}</span>;
}

export function emptyDraft(partial: Partial<ProductDraft> = {}): ProductDraft {
  const cat = partial.cat ?? "베이스";
  return {
    cat,
    type: POUCH_TYPES[cat][0][0],
    brand: "",
    name: "",
    shade: "",
    color: "#EF8E8A",
    ...partial,
  };
}

const norm = (t?: string | null) => (t ?? "").toLowerCase().replace(/\s+/g, "");

/**
 * 제품 등록·수정 시트 (POUCH-002·003·005·006).
 * 카테고리 → 종류 → 브랜드·제품명 → 호수 목록 선택 / 직접 입력 + 색상(선택).
 * 저장하면 세션 파우치에 반영하고 onSaved(저장된 제품)를 부른다.
 */
export function ProductSheet({
  draft,
  onClose,
  onSaved,
  /** 데모: 호수 목록 조회 실패 상태로 연다 */
  initialFail = false,
}: {
  draft: ProductDraft;
  onClose: () => void;
  onSaved?: (item: PouchItem, isNew: boolean) => void;
  initialFail?: boolean;
}) {
  const { state, update } = useSession();
  const [f, setF] = useState<ProductDraft>(draft);
  const [shOpen, setShOpen] = useState(initialFail);
  const [shFail, setShFail] = useState(initialFail);
  const [custom, setCustom] = useState(
    !!draft.custom || (!!draft.shade && !SHADES[draft.cat]?.some((s) => s[0] === draft.shade)),
  );
  const [delAsk, setDelAsk] = useState(false);

  const isEdit = !!f.id;
  const ready = !!f.brand.trim() && !!f.name.trim();
  const noShade = NO_SHADE_CATS.includes(f.cat);
  const list = SHADES[f.cat] ?? SHADES["립"];
  const cur = list.find((s) => s[0] === f.shade);
  const dup =
    ready &&
    state.pouch.some(
      (p) =>
        p.id !== f.id &&
        norm(p.brand) === norm(f.brand) &&
        norm(p.name) === norm(f.name) &&
        norm(p.shade) === norm(f.shade),
    );
  const canSave = ready && !dup;
  const noColor = custom && !f.color;

  const patch = (o: Partial<ProductDraft>) => setF((p) => ({ ...p, ...o }));

  const save = () => {
    if (!canSave) return;
    const item: PouchItem = {
      id: f.id ?? `p${Date.now()}`,
      cat: f.cat,
      type: f.type,
      brand: f.brand.trim(),
      name: f.name.trim(),
      shade: f.shade,
      color: f.color ?? null,
    };
    update((prev) => ({
      pouch: isEdit ? prev.pouch.map((p) => (p.id === item.id ? item : p)) : [item, ...prev.pouch],
    }));
    onSaved?.(item, !isEdit);
    onClose();
  };

  const remove = () => {
    update((prev) => ({ pouch: prev.pouch.filter((p) => p.id !== f.id) }));
    onClose();
  };

  return (
    <Modal
      open
      align="bottom"
      // 삭제 확인이 떠 있을 때 Esc가 시트까지 닫아 입력을 날리지 않게 한다
      onClose={delAsk ? undefined : onClose}
      label={isEdit ? "제품 수정" : "새 제품 등록"}
      overlayClassName="z-30 animate-fade"
      className="relative flex max-h-[92dvh] flex-col gap-6 overflow-y-auto rounded-t-[32px] px-10 pt-4 pb-9 shadow-none"
    >
      <span className="h-1.5 w-14 shrink-0 self-center rounded-full bg-line" />
      <div className="flex items-center justify-between">
        <h2 className="font-display text-[34px] text-ink">
          {isEdit ? "제품 수정" : "새 제품 등록"}
        </h2>
        <button type="button" onClick={onClose} className="text-[20px] font-bold text-mute">
          닫기
        </button>
      </div>

      <div className="flex flex-col gap-2.5">
        <Label>카테고리</Label>
        <div className="flex flex-wrap gap-2">
          {POUCH_CATS.map((c) => {
            const on = f.cat === c;
            return (
              <button
                key={c}
                type="button"
                onClick={() => {
                  patch({ cat: c as PouchCat, type: POUCH_TYPES[c][0][0], shade: "" });
                  setShOpen(false);
                  setCustom(false);
                }}
                className={cn(
                  "flex h-[52px] items-center rounded-full border-2 px-[22px] text-[19px] font-bold",
                  on ? "border-navy bg-navy text-white" : "border-line bg-white text-ink",
                )}
                aria-pressed={on}
              >
                {c}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-col gap-2.5">
        <Label>종류</Label>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {POUCH_TYPES[f.cat].map(([label]) => {
            const on = typeOf(f)[0] === label;
            return (
              <button
                key={label}
                type="button"
                onClick={() => patch({ type: label })}
                className={cn(
                  "flex w-28 shrink-0 flex-col items-center gap-1.5 rounded-[18px] border-2 px-2 py-2.5",
                  on ? "border-navy bg-ice-pale" : "border-line bg-white",
                )}
                aria-pressed={on}
              >
                <Illustration item={{ cat: f.cat, type: label }} color={f.color} size={64} />
                <span
                  className={cn(
                    "text-center text-[15px] leading-[1.25] text-ink",
                    on ? "font-extrabold" : "font-semibold",
                  )}
                >
                  {label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-3">
        <label className="flex min-w-0 flex-col gap-2">
          <Label>브랜드</Label>
          <input
            value={f.brand}
            onChange={(e) => patch({ brand: e.target.value })}
            placeholder="예) 클리오"
            className="h-[68px] w-full min-w-0 rounded-[18px] border-2 border-line px-[22px] text-[22px] font-semibold text-ink outline-none focus:border-navy"
          />
        </label>
        <label className="flex min-w-0 flex-col gap-2">
          <Label>제품명</Label>
          <input
            value={f.name}
            onChange={(e) => patch({ name: e.target.value })}
            placeholder="예) 킬커버 파운웨어 쿠션"
            className="h-[68px] w-full min-w-0 rounded-[18px] border-2 border-line px-[22px] text-[22px] font-semibold text-ink outline-none focus:border-navy"
          />
        </label>
      </div>

      {!noShade && (
        <div className="flex flex-col gap-2">
          <span className="flex items-baseline gap-2">
            <Label>호수 · 컬러</Label>
            <span className="text-[14px] text-mute">
              {ready ? `${list.length}개 컬러` : "선택"}
            </span>
          </span>
          {!ready ? (
            <div className="flex h-[68px] items-center gap-3 rounded-[18px] border-2 border-dashed border-line bg-cream-2 px-[22px] text-[19px] font-semibold text-ash-3">
              <Search className="size-5" strokeWidth={2.2} aria-hidden />
              브랜드와 제품명을 입력하면 컬러가 나와요
            </div>
          ) : (
            <div
              className={cn(
                "overflow-hidden rounded-[18px] border-2 transition-colors",
                shOpen ? "border-navy" : "border-line",
              )}
            >
              <button
                type="button"
                onClick={() => setShOpen((o) => !o)}
                className="flex h-16 w-full items-center gap-3.5 pr-[18px] pl-4 text-left"
                aria-expanded={shOpen}
              >
                <span
                  className="size-9 shrink-0 rounded-full shadow-[inset_0_0_0_1px_rgba(0,0,0,.08)]"
                  style={{ background: cur ? cur[1] : "var(--color-cream)" }}
                />
                <span
                  className={cn(
                    "min-w-0 flex-1 truncate text-[21px] font-bold",
                    cur || f.shade ? "text-ink" : "text-ash-3",
                  )}
                >
                  {cur ? cur[0] : f.shade ? `직접 입력 · ${f.shade}` : "컬러를 선택해 주세요"}
                </span>
                <ChevronDown
                  className={cn(
                    "size-[22px] text-mute transition-transform",
                    shOpen && "rotate-180",
                  )}
                  strokeWidth={2.4}
                  aria-hidden
                />
              </button>
              {shOpen && shFail && (
                <div className="flex flex-wrap items-center gap-3 border-t border-line px-[18px] py-5">
                  <span className="min-w-[200px] flex-1 text-[18px] font-semibold text-navy">
                    컬러 목록을 불러오지 못했어요
                  </span>
                  <button
                    type="button"
                    onClick={() => setShFail(false)}
                    className="flex h-12 items-center rounded-full bg-ink px-5 text-[16px] font-bold text-white"
                  >
                    다시 시도
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      patch({ shade: "", color: null });
                      setShOpen(false);
                      setCustom(true);
                      setShFail(false);
                    }}
                    className="flex h-12 items-center rounded-full border-[1.5px] border-line-2 px-5 text-[16px] font-bold text-ink"
                  >
                    직접 입력
                  </button>
                </div>
              )}
              {shOpen && !shFail && (
                <div className="flex max-h-[300px] animate-fade flex-col overflow-y-auto border-t border-line">
                  {list.map(([label, color]) => {
                    const on = cur?.[0] === label;
                    return (
                      <button
                        key={label}
                        type="button"
                        onClick={() => {
                          patch({ shade: label, color });
                          setShOpen(false);
                          setCustom(false);
                        }}
                        className={cn(
                          "flex min-h-[60px] items-center gap-3.5 pr-[18px] pl-4 text-left hover:bg-ice-pale",
                          on && "bg-ice-pale",
                        )}
                      >
                        <span
                          className="size-8 shrink-0 rounded-full"
                          style={{
                            background: color,
                            boxShadow:
                              color === "#FFFFFF"
                                ? "inset 0 0 0 1px rgba(0,0,0,.15)"
                                : "inset 0 0 0 1px rgba(0,0,0,.08)",
                          }}
                        />
                        <span
                          className={cn(
                            "min-w-0 flex-1 text-[19px] text-ink",
                            on ? "font-bold" : "font-semibold",
                          )}
                        >
                          {label}
                        </span>
                        {on && (
                          <Check className="size-[22px] text-navy" strokeWidth={2.6} aria-hidden />
                        )}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => {
                      patch({ shade: "", color: null });
                      setShOpen(false);
                      setCustom(true);
                    }}
                    className="flex min-h-[60px] items-center gap-3.5 border-t border-dashed border-line pr-[18px] pl-4 text-[18px] font-bold text-navy hover:bg-ice-pale"
                  >
                    <Pencil className="size-5" strokeWidth={2.4} aria-hidden />
                    목록에 없어요 · 직접 입력
                  </button>
                </div>
              )}
            </div>
          )}
          {ready && custom && (
            <>
              <input
                value={f.shade ?? ""}
                onChange={(e) => patch({ shade: e.target.value })}
                placeholder="예) 21N 린넨 · 03 로지"
                className="h-[68px] w-full min-w-0 rounded-[18px] border-2 border-line px-[22px] text-[22px] font-semibold text-ink outline-none focus:border-navy"
              />
              <div className="mt-1.5 flex flex-col gap-2.5">
                <Label>색상 (선택)</Label>
                <div className="flex flex-wrap items-center gap-2.5">
                  {SHADE_COLORS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => patch({ color: c })}
                      aria-label={`색상 ${c}`}
                      aria-pressed={f.color === c}
                      className="size-11 rounded-full"
                      style={{
                        background: c,
                        boxShadow:
                          f.color === c
                            ? "0 0 0 3px #fff, 0 0 0 5px #0B1430"
                            : "inset 0 0 0 1px rgba(0,0,0,.08)",
                      }}
                    />
                  ))}
                  <button
                    type="button"
                    onClick={() => patch({ color: null })}
                    aria-pressed={noColor}
                    className={cn(
                      "flex h-11 items-center rounded-full border-2 px-4 text-[16px] font-bold text-ink",
                      noColor ? "border-solid border-ink" : "border-dashed border-ash",
                    )}
                  >
                    모르겠어요
                  </button>
                </div>
                {noColor && (
                  <span className="text-[16px] leading-[1.5] text-navy">
                    색상 정보가 없으면 대체 후보에서 빠져요.
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {dup && (
        <div
          className="flex items-center gap-2.5 rounded-2xl bg-ice-pale px-[18px] py-3.5 text-[17px] font-semibold text-navy"
          role="alert"
        >
          <span className="size-2 shrink-0 rounded-full bg-cyan" />
          이미 파우치에 있는 제품이에요 · 같은 제품·호수는 한 번만 등록할 수 있어요
        </div>
      )}

      <div className="flex gap-2.5">
        {isEdit && (
          <button
            type="button"
            onClick={() => setDelAsk(true)}
            className="flex h-20 shrink-0 items-center justify-center rounded-full border-2 border-error/25 px-[30px] text-[21px] font-bold whitespace-nowrap text-error active:scale-[.96]"
          >
            삭제
          </button>
        )}
        <PillButton
          size="hero"
          trailing
          onClick={save}
          disabled={!canSave}
          className="ml-auto min-w-[300px] tracking-[-.01em] disabled:bg-line-3"
        >
          저장
        </PillButton>
      </div>

      <Modal
        open={delAsk}
        onClose={() => setDelAsk(false)}
        className="flex max-w-[520px] flex-col gap-6 px-[30px] pt-8 pb-6"
      >
        <div className="flex flex-col gap-2.5">
          <h3 className="font-display text-[30px] leading-[1.25] text-ink">
            이 제품을 파우치에서 뺄까요?
          </h3>
          <p className="text-[18px] leading-[1.55] text-mute">
            {f.brand} {f.name} · 다음 매칭부터 반영돼요. 이미 끝난 리포트는 바뀌지 않아요.
          </p>
        </div>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => setDelAsk(false)}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[19px] font-bold text-ink"
          >
            취소
          </button>
          <button
            type="button"
            onClick={remove}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full bg-error text-[19px] font-bold text-white"
          >
            삭제
          </button>
        </div>
      </Modal>
    </Modal>
  );
}
