import { describe, expect, it } from "vitest";

import { categoryOfPart, groupIndexOf, groupSteps } from "./step-group";

const step = (category: Parameters<typeof groupSteps>[0][number]["category"], title = "") => ({
  category,
  title,
});

describe("groupSteps", () => {
  it("연속한 같은 카테고리만 묶고 영상 순서를 유지한다", () => {
    const groups = groupSteps([
      step("BASE"),
      step("BASE"),
      step("CHEEK"),
      step("BASE"),
      step("EYE"),
      step("EYE"),
      step("EYE"),
    ]);
    expect(groups.map((g) => [g.label, g.start, g.end])).toEqual([
      ["피부", 0, 2],
      ["볼", 2, 3],
      ["피부", 3, 4],
      ["눈", 4, 7],
    ]);
  });

  it("카테고리를 모르는 단계는 하나씩 두고 단계 이름을 쓴다", () => {
    const groups = groupSteps([step(null, "스킨케어 패드"), step(null, "토너"), step("LIP")]);
    expect(groups.map((g) => [g.label, g.start, g.end])).toEqual([
      ["스킨케어 패드", 0, 1],
      ["토너", 1, 2],
      ["입술", 2, 3],
    ]);
  });

  it("단계가 없으면 묶음도 없다", () => {
    expect(groupSteps([])).toEqual([]);
  });

  it("묶음 키를 주면 연속한 같은 키만 묶고 키가 없는 단계는 따로 둔다", () => {
    const withProduct = (category: Parameters<typeof step>[0], product: string | null) => ({
      ...step(category),
      product,
    });
    const steps = [
      withProduct("EYE", "애교빔 펜슬"),
      withProduct("EYE", "리얼아이팔레트"),
      withProduct("EYE", "리얼아이팔레트"),
      withProduct("EYE", "펜슬 라이너"),
      withProduct(null, null),
      withProduct(null, null),
      withProduct("BASE", "컨실러 팔레트"),
      withProduct("CHEEK", "컨실러 팔레트"),
    ];
    const groups = groupSteps(steps, (s) => s.product);
    expect(groups.map((g) => [g.label, g.start, g.end])).toEqual([
      ["눈", 0, 1],
      ["눈", 1, 3],
      ["눈", 3, 4],
      ["", 4, 5],
      ["", 5, 6],
      ["피부", 6, 8],
    ]);
  });
});

describe("groupIndexOf", () => {
  it("단계가 들어 있는 묶음을 찾는다", () => {
    const groups = groupSteps([step("BASE"), step("BASE"), step("LIP")]);
    expect([0, 1, 2, 3].map((i) => groupIndexOf(groups, i))).toEqual([0, 0, 1, -1]);
  });
});

describe("categoryOfPart", () => {
  it("서버와 같은 규칙으로 카테고리를 정하고 모르는 이름은 null이다", () => {
    expect(categoryOfPart("contour")).toBe("CHEEK");
    expect(categoryOfPart("other")).toBeNull();
    expect(categoryOfPart("toString")).toBeNull();
  });
});
