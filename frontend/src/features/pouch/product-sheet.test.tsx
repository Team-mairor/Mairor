// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const session = vi.hoisted(() => ({
  setPouch: vi.fn(),
  expireSession: vi.fn(),
  state: {
    loggedIn: true,
    email: "test@example.com",
    pouch: [{ id: "pouch-1", cat: "립", brand: "브랜드", name: "틴트" }],
  },
}));
const pouchApi = vi.hoisted(() => ({
  deletePouchItem: vi.fn(),
  useCategories: vi.fn(() => ({ items: [], error: null, retry: vi.fn() })),
  useProductSuggestions: vi.fn(() => []),
}));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock("@/domain/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/domain/session")>()),
  useAuth: () => session.state,
  useMyPouch: () => ({ pouch: session.state.pouch, setPouch: session.setPouch }),
  useSessionActions: () => ({ expireSession: session.expireSession }),
}));
vi.mock("@/domain/pouch/pouch-api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/domain/pouch/pouch-api")>()),
  deletePouchItem: pouchApi.deletePouchItem,
  useCategories: pouchApi.useCategories,
  useProductSuggestions: pouchApi.useProductSuggestions,
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import type { ProductDraft } from "@/domain/pouch/draft";

import { ProductSheet } from "./product-sheet";

let root: Root;
let element: HTMLDivElement;
const draft: ProductDraft = {
  id: "pouch-1",
  cat: "립",
  brand: "브랜드",
  name: "틴트",
  shade: "01 로즈",
  color: null,
};
const onClose = vi.fn();

async function mount() {
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  await act(async () => {
    root.render(<ProductSheet draft={draft} onClose={onClose} />);
  });
}

async function clickButton(label: string, scope: ParentNode = element) {
  const button = [...scope.querySelectorAll("button")].find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  if (!button) throw new Error(`${label} 버튼이 없습니다`);
  await act(async () => button.click());
}

function inputFor(label: string) {
  const input = [...element.querySelectorAll("label")]
    .find((candidate) => candidate.textContent?.includes(label))
    ?.querySelector("input");
  if (!input) throw new Error(`${label} 입력칸이 없습니다`);
  return input;
}

async function type(input: HTMLInputElement, value: string) {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.clearAllMocks();
  pouchApi.deletePouchItem.mockResolvedValue(undefined);
});

afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
});

describe("파우치 제품 삭제 확인", () => {
  it("확인창을 열어도 다이얼로그 배경은 하나만 표시한다", async () => {
    await mount();
    await clickButton("삭제");

    expect(element.querySelectorAll('[role="dialog"]')).toHaveLength(1);
    expect(element.textContent).toContain("이 제품을 파우치에서 뺄까요?");
  });

  it("취소하면 삭제 확인만 닫고 제품 시트는 유지한다", async () => {
    await mount();
    await clickButton("삭제");
    await clickButton("취소");

    expect(element.textContent).not.toContain("이 제품을 파우치에서 뺄까요?");
    expect(element.textContent).toContain("제품 수정");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("삭제하면 API를 호출하고 제품 시트를 닫는다", async () => {
    await mount();
    await clickButton("삭제");
    const confirmation = [...element.querySelectorAll('[role="dialog"]')].at(-1);
    if (!confirmation?.textContent?.includes("이 제품을 파우치에서 뺄까요?"))
      throw new Error("삭제 확인창이 없습니다");
    await clickButton("삭제", confirmation);

    expect(pouchApi.deletePouchItem).toHaveBeenCalledWith("pouch-1");
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("배경을 누르면 삭제 확인창만 닫고 제품 시트는 유지한다", async () => {
    await mount();
    await clickButton("삭제");

    const dialog = element.querySelector('[role="dialog"]');
    const overlay = dialog?.parentElement;
    if (!overlay) throw new Error("삭제 확인창을 찾을 수 없습니다");
    await act(async () => overlay.click());

    expect(element.querySelector('[role="dialog"]')?.textContent).not.toContain(
      "이 제품을 파우치에서 뺄까요?",
    );
    expect(element.querySelector('[role="dialog"]')?.textContent).toContain("제품 수정");
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("파우치 제품 입력", () => {
  it("상품명을 직접 입력하면 입력값을 유지한다", async () => {
    await mount();
    const input = inputFor("제품명");

    await type(input, "킬커버 파운웨어 쿠션");

    expect(input.value).toBe("킬커버 파운웨어 쿠션");
  });

  it("한글 조합 중에는 자동완성을 멈추고 조합이 끝난 값을 유지한다", async () => {
    await mount();
    const input = inputFor("제품명");

    await act(async () =>
      input.dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true })),
    );
    await type(input, "쿠션");
    expect(pouchApi.useProductSuggestions).toHaveBeenLastCalledWith(null);

    await act(async () =>
      input.dispatchEvent(new CompositionEvent("compositionend", { bubbles: true })),
    );

    expect(input.value).toBe("쿠션");
  });
});
