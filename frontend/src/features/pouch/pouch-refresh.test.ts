import { describe, expect, it } from "vitest";

import { awaitsCatalog, samePouch } from "./pouch-refresh";
import { emptyDraft } from "./product-sheet";

const item = (o: Parameters<typeof emptyDraft>[0] = {}) => ({ id: "p1", ...emptyDraft(o) });

describe("awaitsCatalog", () => {
  it("카탈로그에 연결되지 않은 항목이 하나라도 있으면 기다린다", () => {
    expect(awaitsCatalog([item({ productId: "a" }), item({ productId: null })])).toBe(true);
    expect(awaitsCatalog([item()])).toBe(true);
  });

  it("모두 연결됐거나 비어 있으면 기다리지 않는다", () => {
    expect(awaitsCatalog([item({ productId: "a" })])).toBe(false);
    expect(awaitsCatalog([])).toBe(false);
  });
});

describe("samePouch", () => {
  const base = item({ brand: "롬앤", name: "퍼지", color: "#C0FFEE", productId: null });

  it("보이는 값이 같으면 같다. 없는 값은 null 과 같다", () => {
    expect(samePouch([base], [{ ...base }])).toBe(true);
    expect(samePouch([{ ...base, color: undefined }], [{ ...base, color: null }])).toBe(true);
  });

  it("색·연결·개수가 바뀌면 다르다", () => {
    expect(samePouch([base], [{ ...base, color: "#BE5953" }])).toBe(false);
    expect(samePouch([base], [{ ...base, productId: "p9", shadeId: "s9" }])).toBe(false);
    expect(samePouch([base], [])).toBe(false);
  });
});
