import { describe, expect, it } from "vitest";

import { draftType, patchDraft, pickSuggestion, saveBody, suggestQuery, toUpdate } from "./draft";
import { emptyDraft } from "./draft";

const CODES = ["LIP_TINT", "LIPSTICK"];
/** 카탈로그 호수로 저장된 항목 */
const linked = emptyDraft({
  id: "pi1",
  cat: "립",
  type: "LIP_TINT",
  brand: "Mairor Sample",
  name: "Water Gel Tint",
  shade: "01 Coral",
  color: "#F2665A",
  productId: "p1",
  shadeId: "s1",
});

describe("draftType", () => {
  it("새로 고를 때는 첫 종류, 목록에 없는 저장값은 선택 없음", () => {
    expect(draftType(undefined, CODES)).toBe("LIP_TINT");
    expect(draftType("LIPSTICK", CODES)).toBe("LIPSTICK");
    expect(draftType("UNKNOWN", CODES)).toBeUndefined();
  });
});

describe("patchDraft", () => {
  it("같은 값을 다시 고르면 카탈로그 연결을 유지한다", () => {
    expect(patchDraft(linked, { type: "LIP_TINT" }, CODES)).toMatchObject({
      productId: "p1",
      shadeId: "s1",
    });
    expect(patchDraft(linked, { brand: "Mairor Sample" }, CODES).shadeId).toBe("s1");
    expect(patchDraft(linked, { brand: "Mairor Sample " }, CODES).shadeId).toBe("s1");
  });

  it("새 등록에서 기본으로 보이는 종류를 눌러도 연결을 유지한다", () => {
    const picked = { ...linked, id: undefined, type: undefined };
    expect(patchDraft(picked, { type: "LIP_TINT" }, CODES).shadeId).toBe("s1");
  });

  it("호수·색만 바꾸면 연결을 유지한다", () => {
    expect(patchDraft(linked, { color: "#000000" }, CODES).productId).toBe("p1");
  });

  it("제품을 정하는 값이 바뀌면 연결을 끊고 호수는 남긴다", () => {
    for (const o of [
      { brand: "Other" },
      { name: "Other" },
      { type: "LIPSTICK" },
      { cat: "아이" as const },
    ]) {
      expect(patchDraft(linked, o, CODES)).toMatchObject({
        productId: null,
        shadeId: null,
        shade: "01 Coral",
      });
    }
  });
});

describe("saveBody", () => {
  it("카탈로그 호수를 골랐으면 CATALOG", () => {
    expect(saveBody(linked, "LIP_TINT", "p1", true)).toEqual({
      registrationMode: "CATALOG",
      type: "LIP_TINT",
      productId: "p1",
      shadeId: "s1",
    });
  });

  it("호수 없는 분류는 제품만 있으면 CATALOG이고 shadeId를 보내지 않는다", () => {
    const toner = emptyDraft({ cat: "스킨케어", type: "TONER", brand: "B", name: "N" });
    expect(saveBody(toner, "TONER", "p2", false)).toEqual({
      registrationMode: "CATALOG",
      type: "TONER",
      productId: "p2",
    });
  });

  it("연결이 끊긴 MANUAL은 화면에 남은 호수·색을 보낸다", () => {
    const cut = patchDraft(linked, { brand: " Other " }, CODES);
    expect(saveBody(cut, "LIP_TINT", null, true)).toEqual({
      registrationMode: "MANUAL",
      category: "LIP",
      type: "LIP_TINT",
      brand: "Other",
      name: "Water Gel Tint",
      shadeName: "01 Coral",
      colorHex: "#F2665A",
    });
  });

  it("호수 없는 분류의 MANUAL에는 호수·색을 넣지 않는다", () => {
    const body = saveBody(
      emptyDraft({ cat: "도구", type: "BRUSH", brand: "B", name: "N" }),
      "BRUSH",
      null,
      false,
    );
    expect(body).not.toHaveProperty("shadeName");
    expect(body).not.toHaveProperty("colorHex");
  });

  it("수정 본문의 MANUAL은 registrationMode를 빼고, CATALOG는 그대로", () => {
    const manual = saveBody({ ...linked, shadeId: null }, "LIP_TINT", null, true);
    expect(toUpdate(manual)).not.toHaveProperty("registrationMode");
    const catalog = saveBody(linked, "LIP_TINT", "p1", true);
    expect(toUpdate(catalog)).toBe(catalog);
  });
});

describe("제품 후보", () => {
  const sug = {
    productId: "p9",
    brand: "롬앤",
    name: "블러 퍼지 틴트 #오리지널",
    category: "LIP",
    type: "LIP_TINT",
  };

  it("이름이 2자 미만이거나 이미 연결된 입력은 묻지 않는다", () => {
    const base = emptyDraft({ cat: "립", brand: "롬앤", name: "퍼" });
    expect(suggestQuery(base, "LIP_TINT")).toBeNull();
    expect(suggestQuery({ ...base, name: "퍼지" }, "LIP_TINT")).not.toBeNull();
    expect(suggestQuery({ ...base, name: "퍼지", productId: "p1" }, "LIP_TINT")).toBeNull();
    expect(suggestQuery({ ...base, name: " 퍼  " }, "LIP_TINT")).toBeNull();
  });

  it("브랜드를 적었으면 함께 보내고, 분류·종류로 좁힌다", () => {
    const f = emptyDraft({ cat: "립", brand: " 롬앤 ", name: " 퍼지 " });
    expect(suggestQuery(f, "LIP_TINT")).toEqual({
      q: "롬앤 퍼지",
      category: "LIP",
      type: "LIP_TINT",
    });
    expect(suggestQuery({ ...f, brand: "" }, undefined)).toEqual({ q: "퍼지", category: "LIP" });
  });

  it("후보를 고르면 브랜드·제품명·종류를 채우고 그 제품에 연결하며 호수는 비운다", () => {
    const typed = emptyDraft({ cat: "립", brand: "", name: "퍼지", shade: "02", color: "#111111" });
    expect(pickSuggestion(typed, sug, CODES)).toMatchObject({
      brand: "롬앤",
      name: "블러 퍼지 틴트 #오리지널",
      type: "LIP_TINT",
      productId: "p9",
      shadeId: null,
      shade: "",
      color: null,
    });
  });

  it("목록에 없는 종류는 바꾸지 않는다", () => {
    const typed = emptyDraft({ cat: "립", type: "LIPSTICK", name: "퍼지" });
    expect(pickSuggestion(typed, { ...sug, type: "OTHER" }, CODES).type).toBe("LIPSTICK");
  });
});
