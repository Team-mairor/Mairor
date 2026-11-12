"use client";

import { Check, ChevronDown, Pencil, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { useSession } from "@/features/session";
import {
  ApiError,
  errorMessage,
  failText,
  isAbortError,
  type Product,
  type Shade,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import { CAT_CODE, POUCH_CATS, SHADE_COLORS, type PouchCat, type PouchItem } from "./catalog";
import { draftType, patchDraft, saveBody, toUpdate } from "./draft";
import { Illustration } from "./illustration";
import {
  createPouchItem,
  deletePouchItem,
  fromApi,
  getProduct,
  searchProduct,
  updatePouchItem,
  useCategories,
} from "./pouch-api";

export type ProductDraft = Omit<PouchItem, "id"> & { id?: string; custom?: boolean };

function Label({ children }: { children: React.ReactNode }) {
  return <span className="text-[15px] font-bold text-mute">{children}</span>;
}

export function emptyDraft(partial: Partial<ProductDraft> = {}): ProductDraft {
  return { cat: "베이스", brand: "", name: "", shade: "", color: null, ...partial };
}

const norm = (t?: string | null) => (t ?? "").toLowerCase().replace(/\s+/g, "");

/** 호수의 대표 색. 팔레트는 쓸 수 있는 첫 칸 */
const shadeHex = (s: Shade) => s.colors.find((c) => c.color)?.color?.hex ?? null;

/** 제품 찾기 결과. key(분류·종류·브랜드·제품명)가 지금 입력과 다르면 지난 결과로 보고 버린다 */
type Lookup =
  | { key: string; status: "loading" }
  | { key: string; status: "ready"; product: Product | null }
  | { key: string; status: "error" };

/** 서버 오류를 시트에 보여 줄 문구로. 입력 조합 오류는 개발자용 문구라 바꿔 보여 준다 */
function saveFailText(e: unknown) {
  if (e instanceof ApiError && e.code.startsWith("POUCH_INVALID"))
    return "제품 정보를 저장하지 못했어요. 컬러를 다시 고르거나 직접 입력으로 저장해 주세요.";
  return failText(e);
}

/** 제품 등록·수정 시트. 저장 본문은 draft.ts, 서버 응답으로 세션 파우치를 바꾼다 */
export function ProductSheet({
  draft,
  onClose,
  onSaved,
}: {
  draft: ProductDraft;
  onClose: () => void;
  onSaved?: (item: PouchItem, isNew: boolean) => void;
}) {
  const router = useRouter();
  const { state, update, expireSession } = useSession();
  const cats = useCategories();
  const [f, setF] = useState<ProductDraft>(draft);
  // 컬러 목록을 연 때의 key. 입력(분류·종류·브랜드·제품명)이 바뀌면 저절로 닫힌다
  const [shKey, setShKey] = useState<string | null>(null);
  // 호수를 직접 입력한 항목(카탈로그 호수 연결 없음)은 직접 입력 칸을 펼쳐 둔다
  const [custom, setCustom] = useState(!!draft.custom || (!!draft.shade && !draft.shadeId));
  const [delAsk, setDelAsk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [fail, setFail] = useState<string | null>(null);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const lookupCtl = useRef<AbortController | null>(null);
  useEffect(() => () => lookupCtl.current?.abort(), []);

  const isEdit = !!f.id;
  const category = cats.items?.find((c) => c.code === CAT_CODE[f.cat]);
  const types = category?.types ?? [];
  const codes = types.map((t) => t.code);
  const type = draftType(f.type, codes);
  const shadeSelectable = category?.shadeSelectable ?? true;
  const ready = !!f.brand.trim() && !!f.name.trim();
  const key = `${f.cat}|${type}|${f.brand.trim()}|${f.name.trim()}`;
  const found = lookup?.key === key ? lookup : null;
  const shOpen = shKey === key;
  const product = found?.status === "ready" ? found.product : null;
  const shades = product?.shades ?? [];
  const dup =
    ready &&
    state.pouch.some(
      (p) =>
        p.id !== f.id &&
        norm(p.brand) === norm(f.brand) &&
        norm(p.name) === norm(f.name) &&
        norm(p.shade) === norm(f.shade),
    );
  // 로그인 전에는 서버에 저장할 수 없어 읽기만 한다
  const guest = !state.loggedIn;
  const canSave = ready && !!type && !dup && !busy && !guest;
  const noColor = custom && !f.color;

  const patch = (o: Partial<ProductDraft>) => {
    setFail(null);
    setF((p) => patchDraft(p, o, codes));
  };

  // 401이면 세션이 끝난 것이라 로그인으로 보낸다. 로그인 전(읽기 전용)에는 보내지 않는다
  const goLogin = (e: unknown) => {
    if (!(state.loggedIn && e instanceof ApiError && e.code === "UNAUTHORIZED")) return false;
    expireSession();
    router.replace("/login?expired=basic");
    return true;
  };

  /** 지금 입력의 카탈로그 제품. 연결된 항목은 API-POUCH-002, 아니면 API-POUCH-001 */
  const findProduct = async (): Promise<Product | null> => {
    if (found?.status === "ready") return found.product;
    if (!type) return null;
    lookupCtl.current?.abort();
    const ctl = new AbortController();
    lookupCtl.current = ctl;
    setLookup({ key, status: "loading" });
    try {
      const p = f.productId
        ? await getProduct(f.productId, ctl.signal).catch((e: unknown) => {
            // 카탈로그에서 빠진 제품은 직접 입력으로 안내한다
            if (e instanceof ApiError && e.code === "NOT_FOUND") return null;
            throw e;
          })
        : await searchProduct(
            { category: CAT_CODE[f.cat], type, brand: f.brand.trim(), name: f.name.trim() },
            ctl.signal,
          );
      setLookup({ key, status: "ready", product: p });
      return p;
    } catch (e) {
      if (!isAbortError(e) && !goLogin(e)) setLookup({ key, status: "error" });
      throw e;
    }
  };

  const toggleShades = () => {
    setShKey(shOpen ? null : key);
    if (!shOpen && !found) findProduct().catch(() => {});
  };

  const toCustom = () => {
    patch({ shade: "", color: null, productId: null, shadeId: null });
    setShKey(null);
    setCustom(true);
  };

  // 응답이 오기 전에 로그아웃·계정 변경이 있었으면 그 응답을 지금 파우치에 넣지 않는다
  const owner = state.email;
  const mine = (prev: { loggedIn: boolean; email: string }) =>
    prev.loggedIn && prev.email === owner;

  const save = async () => {
    if (!canSave || !type) return;
    setBusy(true);
    setFail(null);
    try {
      let productId = f.productId ?? null;
      // 호수가 없는 분류는 저장할 때 카탈로그에서 찾아 연결한다. 찾지 못하면 직접 입력으로 저장
      if (!productId && !shadeSelectable && !custom)
        productId = (await findProduct().catch(() => null))?.productId ?? null;
      const body = saveBody(f, type, productId, shadeSelectable);
      const id = f.id;
      const res = id ? await updatePouchItem(id, toUpdate(body)) : await createPouchItem(body);
      const item = fromApi(res.item);
      update((prev) =>
        !mine(prev)
          ? {}
          : {
              pouch: isEdit
                ? prev.pouch.map((p) => (p.id === item.id ? item : p))
                : [item, ...prev.pouch.filter((p) => p.id !== item.id)],
            },
      );
      onSaved?.(item, !isEdit);
      onClose();
    } catch (e) {
      if (!goLogin(e)) setFail(saveFailText(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    const id = f.id;
    if (!id) return;
    setBusy(true);
    try {
      await deletePouchItem(id);
    } catch (e) {
      // 이미 지워진 항목(404)은 지운 것으로 본다
      if (!(e instanceof ApiError && e.code === "NOT_FOUND")) {
        setBusy(false);
        setDelAsk(false);
        if (!goLogin(e)) setFail(errorMessage(e));
        return;
      }
    }
    update((prev) => (mine(prev) ? { pouch: prev.pouch.filter((p) => p.id !== id) } : {}));
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
      className="scrollbar-hidden relative flex max-h-[92dvh] flex-col gap-6 overflow-y-auto rounded-t-[32px] px-10 pt-4 pb-9 shadow-none"
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
                  if (on) return;
                  patch({ cat: c as PouchCat, type: undefined, shade: "", color: null });
                  setShKey(null);
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
        {cats.error ? (
          <div className="flex items-center gap-3 rounded-[18px] border-2 border-line px-[18px] py-4">
            <span className="flex-1 text-[17px] font-semibold text-navy">
              종류 목록을 불러오지 못했어요
            </span>
            <button
              type="button"
              onClick={cats.retry}
              className="flex h-11 items-center rounded-full bg-ink px-5 text-[16px] font-bold text-white"
            >
              다시 시도
            </button>
          </div>
        ) : !cats.items ? (
          <span className="py-3 text-[17px] text-mute">종류를 불러오고 있어요</span>
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {types.map((t) => {
              const on = type === t.code;
              return (
                <button
                  key={t.code}
                  type="button"
                  onClick={() => patch({ type: t.code })}
                  className={cn(
                    "flex w-28 shrink-0 flex-col items-center gap-1.5 rounded-[18px] border-2 px-2 py-2.5",
                    on ? "border-navy bg-ice-pale" : "border-line bg-white",
                  )}
                  aria-pressed={on}
                >
                  <Illustration item={{ cat: f.cat, type: t.code }} color={f.color} size={64} />
                  <span
                    className={cn(
                      "text-center text-[15px] leading-[1.25] text-ink",
                      on ? "font-extrabold" : "font-semibold",
                    )}
                  >
                    {t.label}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-3">
        <label className="flex min-w-0 flex-col gap-2">
          <Label>브랜드</Label>
          <input
            value={f.brand}
            onChange={(e) => patch({ brand: e.target.value })}
            placeholder="예) 클리오"
            maxLength={100}
            className="h-[68px] w-full min-w-0 rounded-[18px] border-2 border-line px-[22px] text-[22px] font-semibold text-ink outline-none focus:border-navy"
          />
        </label>
        <label className="flex min-w-0 flex-col gap-2">
          <Label>제품명</Label>
          <input
            value={f.name}
            onChange={(e) => patch({ name: e.target.value })}
            placeholder="예) 킬커버 파운웨어 쿠션"
            maxLength={200}
            className="h-[68px] w-full min-w-0 rounded-[18px] border-2 border-line px-[22px] text-[22px] font-semibold text-ink outline-none focus:border-navy"
          />
        </label>
      </div>

      {shadeSelectable && (
        <div className="flex flex-col gap-2">
          <span className="flex items-baseline gap-2">
            <Label>호수 · 컬러</Label>
            <span className="text-[14px] text-mute">
              {product && shades.length ? `${shades.length}개 컬러` : "선택"}
            </span>
          </span>
          {!ready || !type ? (
            <div className="flex h-[68px] items-center gap-3 rounded-[18px] border-2 border-dashed border-line bg-cream-2 px-[22px] text-[19px] font-semibold text-ash-3">
              <Search className="size-5" strokeWidth={2.2} aria-hidden />
              {ready ? "종류를 먼저 골라 주세요" : "브랜드와 제품명을 입력하면 컬러가 나와요"}
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
                onClick={toggleShades}
                className="flex h-16 w-full items-center gap-3.5 pr-[18px] pl-4 text-left"
                aria-expanded={shOpen}
              >
                <span
                  className="size-9 shrink-0 rounded-full shadow-[inset_0_0_0_1px_rgba(0,0,0,.08)]"
                  style={{
                    background: f.shade && f.color ? f.color : "var(--color-cream)",
                  }}
                />
                <span
                  className={cn(
                    "min-w-0 flex-1 truncate text-[21px] font-bold",
                    f.shade ? "text-ink" : "text-ash-3",
                  )}
                >
                  {f.shadeId
                    ? f.shade
                    : f.shade
                      ? `직접 입력 · ${f.shade}`
                      : "컬러를 선택해 주세요"}
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
              {shOpen && found?.status === "loading" && (
                <div className="border-t border-line px-[18px] py-5 text-[18px] font-semibold text-mute">
                  컬러를 찾고 있어요
                </div>
              )}
              {shOpen && found?.status === "error" && (
                <div className="flex flex-wrap items-center gap-3 border-t border-line px-[18px] py-5">
                  <span className="min-w-[200px] flex-1 text-[18px] font-semibold text-navy">
                    컬러 목록을 불러오지 못했어요
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setLookup(null);
                      findProduct().catch(() => {});
                    }}
                    className="flex h-12 items-center rounded-full bg-ink px-5 text-[16px] font-bold text-white"
                  >
                    다시 시도
                  </button>
                  <button
                    type="button"
                    onClick={toCustom}
                    className="flex h-12 items-center rounded-full border-[1.5px] border-line-2 px-5 text-[16px] font-bold text-ink"
                  >
                    직접 입력
                  </button>
                </div>
              )}
              {shOpen && found?.status === "ready" && (
                <div className="scrollbar-hidden flex max-h-[300px] animate-fade flex-col overflow-y-auto border-t border-line">
                  {shades.length === 0 && (
                    <span className="px-[18px] pt-4 pb-2 text-[17px] leading-[1.5] text-mute">
                      {product
                        ? "이 제품은 등록된 컬러가 없어요. 직접 입력해 주세요."
                        : "등록된 제품을 찾지 못했어요. 브랜드·제품명을 확인하거나 직접 입력해 주세요."}
                    </span>
                  )}
                  {product &&
                    shades.map((s) => {
                      const on = f.shadeId === s.shadeId;
                      const hex = shadeHex(s);
                      return (
                        <button
                          key={s.shadeId}
                          type="button"
                          onClick={() => {
                            setF((p) => ({
                              ...p,
                              shade: s.name,
                              color: hex,
                              productId: product.productId,
                              shadeId: s.shadeId,
                            }));
                            setFail(null);
                            setShKey(null);
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
                              background: hex ?? "var(--color-cream)",
                              boxShadow: "inset 0 0 0 1px rgba(0,0,0,.15)",
                            }}
                          />
                          <span
                            className={cn(
                              "min-w-0 flex-1 text-[19px] text-ink",
                              on ? "font-bold" : "font-semibold",
                            )}
                          >
                            {s.name}
                          </span>
                          {on && (
                            <Check
                              className="size-[22px] text-navy"
                              strokeWidth={2.6}
                              aria-hidden
                            />
                          )}
                        </button>
                      );
                    })}
                  <button
                    type="button"
                    onClick={toCustom}
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
                maxLength={100}
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

      {(guest || dup || fail) && (
        <div
          className="flex items-center gap-2.5 rounded-2xl bg-ice-pale px-[18px] py-3.5 text-[17px] font-semibold text-navy"
          role="alert"
        >
          <span className="size-2 shrink-0 rounded-full bg-cyan" />
          {guest ? (
            <>
              로그인하면 파우치에 저장할 수 있어요
              <button
                type="button"
                onClick={() => router.push("/login")}
                className="ml-auto shrink-0 font-bold underline"
              >
                로그인
              </button>
            </>
          ) : dup ? (
            "이미 파우치에 있는 제품이에요 · 같은 제품·호수는 한 번만 등록할 수 있어요"
          ) : (
            fail
          )}
        </div>
      )}

      <div className="flex gap-2.5">
        {isEdit && (
          <button
            type="button"
            onClick={() => setDelAsk(true)}
            disabled={busy || guest}
            className="flex h-20 shrink-0 items-center justify-center rounded-full border-2 border-error/25 px-[30px] text-[21px] font-bold whitespace-nowrap text-error active:scale-[.96] disabled:opacity-40"
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
          {busy ? "저장하는 중" : "저장"}
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
            disabled={busy}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full bg-error text-[19px] font-bold text-white"
          >
            {busy ? "지우는 중" : "삭제"}
          </button>
        </div>
      </Modal>
    </Modal>
  );
}
