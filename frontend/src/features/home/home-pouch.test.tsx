// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PouchItem } from "@/domain/pouch";

import { HomePouch } from "./home-pouch";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

let root: Root;
let host: HTMLDivElement;

beforeEach(() => {
  host = document.createElement("div");
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
});

const render = (pouch: PouchItem[]) =>
  act(() =>
    root.render(
      <HomePouch
        pouch={pouch}
        sync={{ status: "ready", retry: () => {} }}
        waiting={false}
        hidden={false}
      />,
    ),
  );
const stickers = () => host.querySelectorAll("button[aria-label$='수정']");

describe("HomePouch", () => {
  it("비었으면 예시 스티커를 흐리게 보여 주고 머리말로 예시임을 알린다", () => {
    render([]);
    expect(host.textContent).toContain("예시 · 제품을 담으면 내 파우치로 바뀌어요");
    expect(stickers().length).toBeGreaterThan(0);
  });

  it("담긴 제품은 위 카드가 많아도 숨기지 않고 스티커로 보여 준다", () => {
    const pouch = Array.from({ length: 5 }, (_, i) => ({
      id: `p${i}`,
      cat: "립" as const,
      brand: "브랜드",
      name: `틴트 ${i}`,
    }));
    render(pouch);
    expect(host.textContent).toContain("내 파우치 · 5개");
    expect(stickers().length).toBe(5);
  });
});
