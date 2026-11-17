"use client";

import { useEffect, useState } from "react";

import {
  api,
  isAbortError,
  type PouchItemResponse,
  type PouchList,
  type PouchRegistrationRequest,
  type PouchUpdateRequest,
  type PouchWriteResponse,
  type Product,
  type ProductCategory,
  type ProductCategoryList,
  type ProductList,
  type ProductSuggestion,
  type ProductSuggestionList,
} from "@/lib/api";

import { catOf, type PouchItem } from "./catalog";

const ITEMS = "/v1/users/me/pouch-items";

/** 서버 항목을 화면 모양으로 */
export function fromApi(p: PouchItemResponse): PouchItem {
  return {
    id: p.pouchItemId,
    cat: catOf(p.category),
    type: p.type,
    brand: p.brand,
    name: p.name,
    shade: p.shadeName ?? undefined,
    color: p.color?.hex ?? null,
    productId: p.productId,
    shadeId: p.shadeId,
  };
}

// ponytail: 분류 목록은 앱을 여는 동안 한 번만 받는다. 실패하면 다음 호출에서 다시 받는다
let categories: Promise<ProductCategory[]> | null = null;

/** GET /v1/product-categories (API-POUCH-008) */
function fetchCategories() {
  categories ??= api
    .get<ProductCategoryList>("/v1/product-categories")
    .then((r) => r.items)
    .catch((e: unknown) => {
      categories = null;
      throw e;
    });
  return categories;
}

/** 분류 목록. 등록 시트가 연다 */
export function useCategories() {
  const [attempt, setAttempt] = useState(0);
  const [items, setItems] = useState<ProductCategory[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    let live = true;
    fetchCategories().then(
      (list) => {
        if (!live) return;
        setItems(list);
        setError(null);
      },
      (e: unknown) => {
        if (live) setError(e);
      },
    );
    return () => {
      live = false;
    };
  }, [attempt]);
  return { items, error, retry: () => setAttempt((n) => n + 1) };
}

/** GET /v1/products (API-POUCH-001). 같은 제품 0~1건, 없으면 null */
export async function searchProduct(
  query: { category: string; type: string; brand: string; name: string },
  signal: AbortSignal,
): Promise<Product | null> {
  const r = await api.get<ProductList>("/v1/products", { query, signal });
  return r.items[0] ?? null;
}

/** GET /v1/products/suggestions (API-POUCH-009). 이름이 비슷한 제품 후보 */
export async function suggestProducts(
  query: { q: string; category?: string; type?: string },
  signal: AbortSignal,
): Promise<ProductSuggestion[]> {
  const r = await api.get<ProductSuggestionList>("/v1/products/suggestions", { query, signal });
  return r.items;
}

const SUGGEST_DELAY_MS = 250;
const NO_SUGGESTIONS: ProductSuggestion[] = [];

/**
 * 입력하는 동안의 제품 후보. 입력이 멈춘 뒤에 묻고, 새 입력이 오면 지난 요청은 취소한다.
 * 후보는 도움일 뿐이라 실패하면 조용히 비운다(직접 입력은 그대로 된다)
 */
export function useProductSuggestions(
  query: { q: string; category?: string; type?: string } | null,
) {
  const q = query?.q ?? null;
  const category = query?.category;
  const type = query?.type;
  const id = q === null ? null : `${category ?? ""}|${type ?? ""}|${q}`;
  // 받은 후보는 어떤 입력에 대한 것인지(id)와 함께 둔다. 입력이 바뀌면 지난 후보는 보이지 않는다
  const [got, setGot] = useState<{ id: string; items: ProductSuggestion[] } | null>(null);
  useEffect(() => {
    if (q === null || id === null) return;
    const ctl = new AbortController();
    const timer = setTimeout(() => {
      suggestProducts({ q, category, type }, ctl.signal).then(
        (items) => setGot({ id, items }),
        (e: unknown) => {
          if (!isAbortError(e)) setGot({ id, items: [] });
        },
      );
    }, SUGGEST_DELAY_MS);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [id, q, category, type]);
  return got && got.id === id ? got.items : NO_SUGGESTIONS;
}

/** GET /v1/products/{productId} (API-POUCH-002) */
export function getProduct(productId: string, signal: AbortSignal) {
  return api.get<Product>(`/v1/products/${encodeURIComponent(productId)}`, { signal });
}

/** GET /v1/users/me/pouch-items/{id} (API-POUCH-005) */
export function getPouchItem(id: string, signal: AbortSignal) {
  return api.get<PouchItemResponse>(`${ITEMS}/${encodeURIComponent(id)}`, { signal });
}

// 끝난(실패 포함) 저장·삭제 수. 목록을 받는 동안 바뀌면 그 목록은 지난 것이다
let writes = 0;
/** 파우치 쓰기(등록·수정·삭제)가 끝난 횟수. 목록 응답이 그 사이 온 쓰기보다 오래됐는지 가릴 때 쓴다 */
export const writeCount = () => writes;
const wrote = <T>(p: Promise<T>) => p.finally(() => writes++);

/** POST (API-POUCH-004) */
export function createPouchItem(body: PouchRegistrationRequest) {
  return wrote(api.post<PouchWriteResponse>(ITEMS, { body }));
}

/** PATCH (API-POUCH-006) */
export function updatePouchItem(id: string, body: PouchUpdateRequest) {
  return wrote(api.patch<PouchWriteResponse>(`${ITEMS}/${encodeURIComponent(id)}`, { body }));
}

/** DELETE (API-POUCH-007). 204 */
export function deletePouchItem(id: string) {
  return wrote(api.delete(`${ITEMS}/${encodeURIComponent(id)}`));
}

/** GET (API-POUCH-003). hasNext=false까지 모두 받는다 */
export async function fetchAllPouch(signal: AbortSignal) {
  const items: PouchItemResponse[] = [];
  for (let page = 0; ; page++) {
    const r = await api.get<PouchList>(ITEMS, { query: { page, size: 100 }, signal });
    items.push(...r.items);
    if (!r.hasNext) return items;
  }
}
