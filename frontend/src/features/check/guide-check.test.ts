import { describe, expect, it } from "vitest";

import type { GuideStepModel } from "@/features/guide";
import type { PouchItem } from "@/features/pouch";
import { createRun } from "@/features/session/run-state";

import { candidatesFor, checkRows, pickCounts, pickOf, withChoice } from "./guide-check";

const step = (stepId: string, extra: Partial<GuideStepModel> = {}): GuideStepModel => ({
  stepId,
  order: 1,
  makeup: "blush",
  label: "블러셔",
  summary: null,
  actions: [],
  doneWhen: null,
  product: { name: "롬앤 베러 댄 치크", shade: "01 쥬시 코랄" },
  matchCategory: "CHEEK",
  previewable: false,
  subSteps: [],
  ...extra,
});

const item = (id: string, extra: Partial<PouchItem> = {}): PouchItem => ({
  id,
  cat: "치크",
  type: "블러셔",
  brand: "브랜드",
  name: `제품 ${id}`,
  color: null,
  ...extra,
});

describe("pickOf", () => {
  const pouch = [item("p1")];

  it("선택이 없으면 고르지 않은 상태다", () => {
    expect(pickOf("s1", {}, pouch)).toEqual({ kind: "undecided" });
  });

  it("고른 파우치 제품 ID를 그대로 돌려준다", () => {
    expect(pickOf("s1", { s1: { kind: "pouch", id: "p1" } }, pouch)).toEqual({
      kind: "picked",
      item: pouch[0],
    });
  });

  it("없이 진행은 건너뜀이다", () => {
    expect(pickOf("s1", { s1: { kind: "none" } }, pouch)).toEqual({ kind: "skipped" });
  });

  it("고른 제품이 파우치에서 지워졌으면 고르지 않은 상태로 본다", () => {
    expect(pickOf("s1", { s1: { kind: "pouch", id: "gone" } }, pouch)).toEqual({
      kind: "undecided",
    });
  });

  it("영상 제품과 이름이 같은 파우치 제품이 있어도 보유로 정하지 않는다", () => {
    const same = [item("p1", { brand: "롬앤", name: "베러 댄 치크" })];
    expect(pickOf("s1", {}, same)).toEqual({ kind: "undecided" });
  });
});

describe("checkRows", () => {
  it("가이드 단계 순서와 stepId를 그대로 쓰고, 다른 단계의 선택은 무시한다", () => {
    const rows = checkRows(
      [step("s2"), step("s5")],
      { s5: { kind: "none" }, old: { kind: "pouch", id: "p1" } },
      [item("p1")],
    );
    expect(rows.map((r) => [r.step.stepId, r.pick.kind, r.suggestion])).toEqual([
      ["s2", "undecided", null],
      ["s5", "skipped", null],
    ]);
    expect(pickCounts(rows)).toEqual({ undecided: 1, picked: 0, skipped: 1 });
  });
});

describe("candidatesFor", () => {
  it("블러셔 단계에는 블러셔만 나온다", () => {
    const pouch = [
      item("blush"),
      item("high", { type: "하이라이터" }),
      item("compact", { type: "컴팩트" }),
      item("lip", { cat: "립", type: "립스틱" }),
    ];
    expect(candidatesFor(step("s1"), pouch).map((p) => p.id)).toEqual(["blush"]);
  });

  it("종류가 없는 제품은 추정하지 않고 뺀다", () => {
    expect(candidatesFor(step("s1"), [item("old", { type: undefined })])).toEqual([]);
  });

  it("색이 없어도 후보에 넣고, 기준색이 없으면 파우치 순서를 지킨다", () => {
    const pouch = [item("a"), item("b", { color: "#EF8E8A" })];
    expect(candidatesFor(step("s1"), pouch).map((p) => p.id)).toEqual(["a", "b"]);
  });

  it("기준색이 있으면 색이 가까운 순이고 색 없는 제품은 뒤로 간다", () => {
    const pouch = [
      item("none"),
      item("far", { color: "#2B2220" }),
      item("near", { color: "#EE8D89" }),
    ];
    expect(candidatesFor(step("s1"), pouch, "#EF8E8A").map((p) => p.id)).toEqual([
      "near",
      "far",
      "none",
    ]);
  });

  it("쉐딩처럼 호환 종류가 정해지지 않은 단계는 후보가 없다", () => {
    expect(candidatesFor(step("s1", { makeup: "contour" }), [item("blush")])).toEqual([]);
  });

  it("단계의 대분류와 파우치 카테고리가 다르면 뺀다", () => {
    expect(candidatesFor(step("s1", { matchCategory: "LIP" }), [item("blush")])).toEqual([]);
  });
});

describe("withChoice", () => {
  it("null이면 선택을 지워 고르지 않은 상태로 되돌린다", () => {
    const before = { s1: { kind: "none" } as const };
    expect(withChoice(before, "s1", null)).toEqual({});
    expect(before).toEqual({ s1: { kind: "none" } });
  });
});

describe("새 실행", () => {
  it("새 실행은 이전 선택 없이 시작한다", () => {
    const run = createRun({ kind: "guide", guideId: "a0000000-0000-4000-8000-000000000001" }, "r2");
    expect(run.choice).toEqual({});
  });
});
