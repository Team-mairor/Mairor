import type { PouchRegistrationRequest, PouchUpdateRequest, ProductSuggestion } from "@/lib/api";

import { CAT_CODE } from "./catalog";
import type { ProductDraft } from "./product-sheet";

/** 화면에 선택돼 보이는 종류. 새로 고를 때만 첫 종류를 기본으로 두고, 목록에 없는 저장값은 비워 다시 고르게 한다 */
export function draftType(type: string | undefined, codes: readonly string[]) {
  return type ? codes.find((c) => c === type) : codes[0];
}

/** 입력 반영. 분류·종류·브랜드·제품명(trim)이 실제로 바뀔 때만 카탈로그 연결을 끊는다 */
export function patchDraft(
  p: ProductDraft,
  o: Partial<ProductDraft>,
  codes: readonly string[],
): ProductDraft {
  const next = { ...p, ...o };
  const moved =
    next.cat !== p.cat ||
    next.brand.trim() !== p.brand.trim() ||
    next.name.trim() !== p.name.trim() ||
    draftType(next.type, codes) !== draftType(p.type, codes);
  return moved ? { ...next, productId: null, shadeId: null } : next;
}

/** 후보를 물을 최소 글자 수(공백 제외). 서버도 2자 미만이면 빈 목록을 준다 */
export const SUGGEST_MIN = 2;

/**
 * 제품명 입력에 대한 후보 요청. 브랜드를 이미 적었으면 함께 보내 좁힌다.
 * 이미 카탈로그 제품에 연결됐거나 입력이 짧으면 묻지 않는다(null)
 */
export function suggestQuery(
  f: Pick<ProductDraft, "cat" | "brand" | "name" | "productId">,
  type: string | undefined,
): { q: string; category: string; type?: string } | null {
  if (f.productId) return null;
  if (f.name.replace(/\s+/g, "").length < SUGGEST_MIN) return null;
  const q = `${f.brand.trim()} ${f.name.trim()}`.trim();
  return { q, category: CAT_CODE[f.cat], ...(type && { type }) };
}

/** 후보를 고른 입력. 브랜드·제품명을 채우고 그 제품에 연결한다. 호수는 다시 고른다 */
export function pickSuggestion(
  p: ProductDraft,
  s: ProductSuggestion,
  codes: readonly string[],
): ProductDraft {
  const next = patchDraft(
    p,
    { brand: s.brand, name: s.name, ...(codes.includes(s.type) && { type: s.type }) },
    codes,
  );
  return { ...next, productId: s.productId, shadeId: null, shade: "", color: null };
}

/** 저장 본문. 카탈로그 제품(+호수 분류면 호수)이 있으면 CATALOG, 아니면 MANUAL. 호수 없는 분류엔 호수·색을 안 보낸다(서버가 거절) */
export function saveBody(
  f: ProductDraft,
  type: string,
  productId: string | null,
  shadeSelectable: boolean,
): PouchRegistrationRequest {
  if (productId && (!shadeSelectable || f.shadeId))
    return {
      registrationMode: "CATALOG",
      type,
      productId,
      ...(shadeSelectable && f.shadeId && { shadeId: f.shadeId }),
    };
  return {
    registrationMode: "MANUAL",
    category: CAT_CODE[f.cat],
    type,
    brand: f.brand.trim(),
    name: f.name.trim(),
    ...(shadeSelectable && { shadeName: f.shade?.trim() || null, colorHex: f.color ?? null }),
  };
}

/** 수정(API-POUCH-006) 본문. MANUAL은 registrationMode 없이 직접 입력 칸만 보낸다 */
export function toUpdate(body: PouchRegistrationRequest): PouchUpdateRequest {
  if (body.registrationMode === "CATALOG") return body;
  const { category, type, brand, name, shadeName, colorHex } = body;
  return { category, type, brand, name, shadeName, colorHex };
}
