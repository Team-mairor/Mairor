// @vitest-environment jsdom
import { act, useLayoutEffect, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GuideModel, GuideStepModel } from "@/features/guide";
import { RunGuideContext } from "@/features/guide/use-guide";
import type { PouchItem } from "@/features/pouch";
import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api } from "@/lib/api";

import { GuideCheck } from "./guide-check-view";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/face", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/face")>()),
  useHiddenVideo: () => {},
}));
vi.mock("@/features/live", () => ({
  GlassPanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LiveTag: () => null,
  LiveNote: () => null,
  RoundBack: ({ onClick, label }: { onClick: () => void; label: string }) => (
    <button type="button" onClick={onClick}>
      {label}
    </button>
  ),
  useLiveState: () => ({ note: null, reason: null, canRender: true }),
}));

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const step = (stepId: string, order: number, extra: Partial<GuideStepModel> = {}) => ({
  stepId,
  order,
  makeup: "blush" as const,
  label: "블러셔",
  summary: null,
  actions: [],
  doneWhen: null,
  product: { name: "롬앤 베러 댄 치크", shade: "01 쥬시 코랄" },
  matchCategory: "CHEEK" as const,
  previewable: false,
  subSteps: [],
  ...extra,
});
const guide: GuideModel = {
  guideId: GUIDE_ID,
  guideVersion: 1,
  videoId: "v",
  youtubeVideoId: null,
  thumbnailUrl: null,
  title: "실제 가이드",
  channelTitle: "채널",
  meshVersion: null,
  steps: [
    step("s2", 1),
    step("s5", 2, { makeup: "lip", label: "립", matchCategory: "LIP", product: null }),
    step("s8", 3, {
      makeup: "highlight",
      label: "하이라이터",
      product: { name: null, shade: "02" },
    }),
  ],
};
const pouch: PouchItem[] = [
  { id: "same", cat: "치크", type: "블러셔", brand: "롬앤", name: "베러 댄 치크", color: null },
  { id: "high", cat: "치크", type: "하이라이터", brand: "B", name: "글로우", color: "#F3E3D3" },
  { id: "tint", cat: "립", type: "립틴트", brand: "C", name: "틴트", color: "#B5706B" },
];

let session: ReturnType<typeof useSession>;
let root: Root;
let element: HTMLDivElement;
function Probe() {
  const value = useSession();
  useLayoutEffect(() => {
    session = value;
  });
  return null;
}
const text = () => element.textContent ?? "";
const button = (label: string, scope: ParentNode = element) => {
  const found = [...scope.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
  if (!found) throw new Error(`${label} 버튼이 없습니다`);
  return found;
};
const click = async (el: HTMLElement) => {
  await act(async () => el.click());
};

beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
    clear: () => saved.clear(),
  });
  vi.clearAllMocks();
  vi.spyOn(api, "get").mockResolvedValue({ user: { email: "t@example.com" }, csrfToken: "c" });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  await act(async () => {
    root.render(
      <SessionProvider seed={{ pouch, reports: [] }}>
        <Probe />
        <RunGuideContext.Provider
          value={{
            search: "",
            load: { status: "ready", guide, checking: false, error: null },
            retry: async () => true,
          }}
        >
          <GuideCheck />
        </RunGuideContext.Provider>
      </SessionProvider>,
    );
  });
  await act(async () => {
    // 로그인 확인 뒤 서버 파우치 목록을 받은 상태
    session.update({ pouch });
    session.startRun({ kind: "guide", guideId: GUIDE_ID });
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("실제 가이드 제품 체크", () => {
  it("가이드 단계와 영상 제품 이름·호수를 그대로 보여 주고 보유·대체를 지어내지 않는다", () => {
    expect(
      [...element.querySelectorAll("[data-step]")].map((e) => e.getAttribute("data-step")),
    ).toEqual(["s2", "s5", "s8"]);
    expect(text()).toContain("롬앤 베러 댄 치크 01 쥬시 코랄");
    expect(text()).toContain("영상에서 제품 정보를 찾지 못했어요");
    expect(text()).toContain("STEP 3 · 하이라이터");
    // 파우치에 같은 이름 제품이 있어도 미확정이다
    expect(text()).toContain("0/3");
    expect(text()).not.toMatch(/보유|대체|추천|내 파우치에 없음/);
  });

  it("고른 파우치 제품 ID를 stepId로 기록하고, 후보는 같은 소분류만 보여 준다", async () => {
    const row = element.querySelector('[data-step="s2"]')!;
    await click(button("고르기", row));
    expect(text()).toContain("베러 댄 치크");
    expect(text()).not.toContain("글로우");
    await click(button("베러 댄 치크"));
    expect(session.state.run.choice).toEqual({ s2: { kind: "pouch", id: "same" } });
    expect(text()).toContain("1/3");
  });

  it("건너뜀과 선택 해제를 구분한다", async () => {
    await click(button("고르기", element.querySelector('[data-step="s5"]')!));
    await click(button("이 제품 없이 진행"));
    expect(session.state.run.choice).toEqual({ s5: { kind: "none" } });
    await click(button("건너뜀"));
    await click(button("바꾸기", element.querySelector('[data-step="s5"]')!));
    await click(button("선택 해제"));
    expect(session.state.run.choice).toEqual({});
  });

  it("고르지 않은 단계가 있어도 시작 때 건너뜀으로 바꾸지 않는다", async () => {
    await click(button("이 조합으로 시작"));
    expect(text()).toContain("고르지 않은 단계 3개는");
    await click(button("건너뛰고 시작"));
    expect(session.state.run.choice).toEqual({});
    expect(router.push).toHaveBeenCalledWith(`/tutorial/guide?guideId=${GUIDE_ID}`);
  });

  it("새 실행에서는 이전 선택이 남지 않는다", async () => {
    await act(async () => {
      session.updateRun({ choice: { s2: { kind: "pouch", id: "same" } } }, session.state.run.id);
    });
    expect(text()).toContain("1/3");
    await act(async () => {
      session.startRun({ kind: "guide", guideId: GUIDE_ID });
    });
    expect(session.state.run.choice).toEqual({});
    expect(text()).toContain("0/3");
  });
});
