import { describe, expect, it } from "vitest";

import { fromApi } from "@/domain/pouch/pouch-api";
import type { PouchItemResponse } from "@/lib/api";

import { illOf } from "./illustration";

const item: PouchItemResponse = {
  pouchItemId: "00000000-0000-4000-8000-000000000301",
  registrationMode: "CATALOG",
  productId: "00000000-0000-4000-8000-000000000101",
  shadeId: "00000000-0000-4000-8000-000000000201",
  brand: "예시 브랜드",
  name: "예시 틴트",
  category: "LIP",
  type: "LIP_TINT",
  shadeName: "01 로즈",
  color: { colorSpace: "sRGB", hex: "#112233", source: "CATALOG", estimated: false },
  colorSource: "CATALOG",
  createdAt: "2026-11-08T00:00:00Z",
  updatedAt: "2026-11-08T00:00:00Z",
};

describe("파우치 응답 변환", () => {
  it("서버 항목을 화면 모양으로 바꾸고 카탈로그 연결을 남긴다", () => {
    expect(fromApi(item)).toEqual({
      id: item.pouchItemId,
      cat: "립",
      type: "LIP_TINT",
      brand: "예시 브랜드",
      name: "예시 틴트",
      shade: "01 로즈",
      color: "#112233",
      productId: item.productId,
      shadeId: item.shadeId,
    });
  });

  it("호수·색이 없으면 shade 없음, color null", () => {
    const p = fromApi({ ...item, shadeName: null, color: null, colorSource: "NONE" });
    expect(p.shade).toBeUndefined();
    expect(p.color).toBeNull();
  });

  it("모르는 종류 코드는 카테고리 기본 그림", () => {
    expect(illOf({ cat: "립", type: "LIP_TINT" }).key).toBe("tint");
    expect(illOf({ cat: "립", type: "LIP_OIL" }).key).toBe("lip");
    expect(illOf({ cat: "치크" }).key).toBe("blush");
  });
});
