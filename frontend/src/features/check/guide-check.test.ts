import { describe, expect, it } from "vitest";

import type { GuideStepModel } from "@/features/guide";
import type { PouchItem } from "@/features/pouch";
import { createRun } from "@/features/session/run-state";

import {
  candidatesFor,
  checkRows,
  choiceOf,
  guidePick,
  pickCounts,
  pickOf,
  swapList,
  userChoice,
  withChoice,
} from "./guide-check";
import type { StepMatch } from "./match-api";

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

  it("없이 진행은 생략이다", () => {
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

const match = (stepId: string, extra: Partial<StepMatch> = {}): StepMatch => ({
  stepId,
  result: "NONE",
  samePouchItemId: null,
  noneReason: "COMPARISON_UNAVAILABLE",
  candidates: [],
  ...extra,
});

describe("guidePick", () => {
  const pouch = [item("p1"), item("p2"), item("p3")];
  const same = match("s1", { result: "SAME", samePouchItemId: "p1", noneReason: null });
  const sub = match("s1", {
    result: "SUBSTITUTE",
    noneReason: null,
    candidates: [
      { pouchItemId: "gone", rank: 1 },
      { pouchItemId: "p2", rank: 2 },
    ],
  });

  it("고른 것이 없으면 서버의 보유·대체를 쓰고, 지워진 후보는 건너뛴다", () => {
    expect(guidePick("s1", {}, pouch, same)).toEqual({ kind: "same", item: pouch[0] });
    expect(guidePick("s1", {}, pouch, sub)).toEqual({ kind: "sub", item: pouch[1] });
  });

  it("직접 고른 제품이 보유 제품이면 보유, 아니면 대체다", () => {
    const chose = (id: string) => ({ s1: { kind: "pouch" as const, id } });
    expect(guidePick("s1", chose("p1"), pouch, same).kind).toBe("same");
    expect(guidePick("s1", chose("p3"), pouch, same)).toEqual({ kind: "sub", item: pouch[2] });
  });

  it("생략을 골랐으면 서버 결과와 상관없이 생략이다", () => {
    expect(guidePick("s1", { s1: { kind: "none" } }, pouch, same)).toEqual({
      kind: "none",
      reason: "skipped",
    });
  });

  it("없음은 서버 이유를 쓰고, 매칭 결과가 없으면 넘겨받은 이유(맞추는 중·실패·대상 아님)를 쓴다", () => {
    const noItems = match("s1", { noneReason: "NO_ITEMS" });
    expect(guidePick("s1", {}, pouch, noItems)).toEqual({ kind: "none", reason: "NO_ITEMS" });
    expect(guidePick("s1", {}, pouch, undefined)).toEqual({ kind: "none", reason: "unsupported" });
    expect(guidePick("s1", {}, pouch, undefined, "pending")).toEqual({
      kind: "none",
      reason: "pending",
    });
  });
});

describe("checkRows", () => {
  it("가이드 단계 순서를 쓰고 상태별로 센다. 대체 후보는 순위순", () => {
    const pouch = [item("p1"), item("p2"), item("p3")];
    const matches = new Map([
      ["s2", match("s2", { result: "SAME", samePouchItemId: "p1", noneReason: null })],
      [
        "s5",
        match("s5", {
          result: "SUBSTITUTE",
          noneReason: null,
          candidates: [
            { pouchItemId: "p3", rank: 2 },
            { pouchItemId: "p2", rank: 1 },
          ],
        }),
      ],
    ]);
    const rows = checkRows([step("s2"), step("s5"), step("s8")], {}, pouch, matches);
    expect(rows.map((r) => [r.step.stepId, r.pick.kind])).toEqual([
      ["s2", "same"],
      ["s5", "sub"],
      ["s8", "none"],
    ]);
    expect(rows[1].candidates.map((p) => p.id)).toEqual(["p2", "p3"]);
    expect(pickCounts(rows)).toEqual({ same: 1, sub: 1, none: 1 });
    expect(rows.map((r) => choiceOf(r.pick))).toEqual([
      { kind: "pouch", id: "p1", auto: true },
      { kind: "pouch", id: "p2", auto: true },
      { kind: "none", auto: true },
    ]);
  });

  it("시작할 때 자동으로 채운 선택은 체크 화면에서 무시하고 서버 매칭을 쓴다", () => {
    const pouch = [item("p1"), item("p2")];
    const match = new Map([
      [
        "s1",
        {
          stepId: "s1",
          result: "SUBSTITUTE" as const,
          samePouchItemId: null,
          noneReason: null,
          candidates: [{ pouchItemId: "p2", rank: 1 }],
        },
      ],
    ]);
    const auto = { s1: { kind: "none" as const, auto: true as const } };
    expect(guidePick("s1", auto, pouch, match.get("s1"))).toMatchObject({ kind: "sub" });
    expect(userChoice(auto, "s1")).toBeUndefined();
    expect(guidePick("s1", { s1: { kind: "none" } }, pouch, match.get("s1"))).toEqual({
      kind: "none",
      reason: "skipped",
    });
  });
});

describe("swapList", () => {
  const pouch = [
    item("p1", { color: "#EF8E8A" }),
    item("p2", { color: "#D9776F" }),
    item("p3", { color: "#C06A66" }),
  ];
  const row = checkRows([step("s5")], {}, pouch, new Map())[0];
  const same = candidatesFor(row.step, pouch).map((p) => p.id);

  it("서버 alternatives를 순위순으로 먼저 쓰고 비교에 쓴 색을 얹는다", () => {
    const m = match("s5", {
      alternatives: [
        { pouchItemId: "p3", rank: 2, matchedColorHex: "#AA0000" },
        { pouchItemId: "p2", rank: 1 },
      ],
    });
    const list = swapList(row, pouch, m);
    expect(list.slice(0, 2).map((p) => p.id)).toEqual(["p2", "p3"]);
    expect(list[1].color).toBe("#AA0000");
  });

  it("서버 후보 뒤에 같은 종류의 색 있는 제품을 붙이고 중복은 없다", () => {
    const m = match("s5", { alternatives: [{ pouchItemId: "p2", rank: 1 }] });
    const ids = swapList(row, pouch, m).map((p) => p.id);
    expect(ids[0]).toBe("p2");
    expect([...ids].sort()).toEqual([...same].sort());
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("alternatives가 비거나 매칭이 없어도 같은 종류 제품은 보여 준다", () => {
    expect(swapList(row, pouch, match("s5", { alternatives: [] })).map((p) => p.id)).toEqual(same);
    expect(swapList(row, pouch, undefined).map((p) => p.id)).toEqual(same);
  });

  it("alternatives 필드가 없는 옛 매칭은 candidates를 먼저 쓴다", () => {
    const legacy = match("s5", { candidates: [{ pouchItemId: "p3", rank: 1 }] });
    expect(swapList(row, pouch, legacy)[0].id).toBe("p3");
  });

  it("파우치에 없는 서버 후보는 건너뛴다", () => {
    const m = match("s5", { alternatives: [{ pouchItemId: "gone", rank: 1 }] });
    expect(swapList(row, pouch, m).map((p) => p.id)).toEqual(same);
  });
});

describe("candidatesFor", () => {
  it("단계의 화장 종류에 맞는 종류만 수동 선택 후보가 된다", () => {
    const pouch = [
      item("blush", { color: "#EF8E8A" }),
      item("high", { type: "하이라이터", color: "#F3E3D3" }),
      item("compact", { type: "컴팩트", color: "#D9B9A0" }),
      item("lip", { cat: "립", type: "립스틱", color: "#C06A66" }),
    ];
    expect(candidatesFor(step("s1"), pouch).map((p) => p.id)).toEqual(["blush"]);
    expect(candidatesFor(step("s1", { makeup: "highlight" }), pouch).map((p) => p.id)).toEqual([
      "high",
    ]);
  });

  it("같은 카테고리여도 종류가 다르면 뺀다 (하이라이터 단계에 블러셔 제외)", () => {
    const blush = [item("blush", { color: "#EF8E8A" })];
    expect(candidatesFor(step("s1", { makeup: "highlight" }), blush)).toEqual([]);
  });

  it("종류가 없는 제품은 후보에서 뺀다", () => {
    const manual = [item("manual", { type: undefined, color: "#EF8E8A" })];
    expect(candidatesFor(step("s1"), manual)).toEqual([]);
  });

  it("대표 색상이 없는 제품은 수동 선택 후보에서 제외한다", () => {
    expect(candidatesFor(step("s1"), [item("old", { color: null })])).toEqual([]);
  });

  it("기준색이 없어도 대표 색상 있는 후보를 파우치 순서로 보여 준다", () => {
    const pouch = [item("a", { color: "#E0A090" }), item("b", { color: "#EF8E8A" })];
    expect(candidatesFor(step("s1"), pouch).map((p) => p.id)).toEqual(["a", "b"]);
  });

  it("기준색이 있으면 대표 색상으로 유사도 순 정렬한다", () => {
    const pouch = [
      item("none", { color: null }),
      item("far", { color: "#2B2220" }),
      item("near", { color: "#EE8D89" }),
    ];
    expect(candidatesFor(step("s1"), pouch, "#EF8E8A").map((p) => p.id)).toEqual(["near", "far"]);
  });

  it("쉐이딩은 후보 종류가 없어 수동 선택 후보도 없다", () => {
    expect(
      candidatesFor(step("s1", { makeup: "contour" }), [item("blush", { color: "#EF8E8A" })]),
    ).toEqual([]);
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
