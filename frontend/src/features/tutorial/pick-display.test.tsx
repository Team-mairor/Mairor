// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StepPick } from "@/domain/check";

import { ProductChip } from "./product-chip";
import { PrepCard } from "./step-cards";

let root: Root;
let element: HTMLDivElement;
const render = async (node: React.ReactNode) => {
  await act(async () => root.render(node));
};
const picked: StepPick = {
  kind: "picked",
  item: { id: "p1", cat: "치크", type: "블러셔", brand: "클리오", name: "프리즘 블러셔" },
};
const info = { title: "블러셔", acts: [{ text: "볼 중앙에 발라요", tip: null }], doneWhen: null };

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
});

describe("영상 제품 정보가 없는 실제 가이드 단계", () => {
  it("제품 칩은 고른 제품을 보여 준다", async () => {
    await render(<ProductChip refProduct={null} mine={null} pick={picked} />);
    expect(element.textContent).toContain("영상 속 제품 정보 없음");
    expect(element.textContent).toContain("클리오 프리즘 블러셔");
  });

  it("고르지 않았으면 준비 카드가 영상 속 제품을 참고하라고 하지 않는다", async () => {
    await render(
      <PrepCard
        step={0}
        total={3}
        info={info}
        refProduct={null}
        match={null}
        pick={{ kind: "undecided" }}
        onStart={() => {}}
      />,
    );
    expect(element.textContent).toContain("설명을 보고 따라 하거나 건너뛸 수 있어요");
    expect(element.textContent).not.toContain("영상 속 제품을 참고해");
    expect(element.textContent).not.toContain("할 일 1가지");
  });

  it("영상 속 제품의 내부 매칭 상태 배지를 준비 카드에 띄우지 않는다", async () => {
    await render(
      <PrepCard
        step={0}
        total={3}
        info={info}
        refProduct={{
          name: "젤리 에어 치크",
          full: "하밍 젤리 에어 치크",
          shade: "02 베리피치",
          color: null,
          state: "unreg",
        }}
        match={null}
        pick={{ kind: "skipped" }}
        onStart={() => {}}
      />,
    );
    expect(element.textContent).toContain("영상 속 제품 · 하밍 젤리 에어 치크 02 베리피치");
    expect(element.textContent).not.toContain("이름만 확인");
  });

  it("게이지 기준 사진을 다 모을 때까지 시작을 막고 진행 수를 보여 준다", async () => {
    await render(
      <PrepCard
        step={0}
        total={3}
        info={info}
        refProduct={null}
        match={null}
        baseline={{ frames: 7, total: 15, ready: false }}
        onStart={() => {}}
      />,
    );
    expect(element.textContent).not.toContain("정면을 봐 주세요");
    const button = element.querySelector("button");
    expect(button?.textContent).toContain("시작하기 (7/15)");
    expect(button?.getAttribute("aria-label")).toBe("시작하기, 준비 7/15");
    expect(button?.querySelector<HTMLElement>("[aria-hidden]")?.style.width).toBe(
      "46.666666666666664%",
    );
    expect(button?.disabled).toBe(true);
  });

  it("기준 사진을 오래 모으지 못하면 게이지 없이 시작할 수 있다", async () => {
    const onStart = vi.fn();
    await render(
      <PrepCard
        step={0}
        total={3}
        info={info}
        refProduct={null}
        match={null}
        baseline={{ frames: 7, total: 15, ready: false, canSkip: true }}
        onStart={onStart}
      />,
    );
    const button = element.querySelector("button")!;
    expect(button.textContent).toContain("게이지 없이 시작 (7/15)");
    expect(button.getAttribute("aria-label")).toBe("게이지 없이 시작, 준비 7/15");
    expect(button.disabled).toBe(false);
    await act(async () => button.click());
    expect(onStart).toHaveBeenCalledOnce();
  });
});
