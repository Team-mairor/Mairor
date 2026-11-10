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
    step("s9", 4, { makeup: "mascara", label: "마스카라", matchCategory: "EYE" }),
  ],
};
const pouch: PouchItem[] = [
  { id: "same", cat: "치크", type: "블러셔", brand: "롬앤", name: "베러 댄 치크", color: null },
  { id: "high", cat: "치크", type: "하이라이터", brand: "B", name: "글로우", color: "#F3E3D3" },
  { id: "tint", cat: "립", type: "립틴트", brand: "C", name: "틴트", color: "#B5706B" },
];

/** 서버 매칭: s2 보유, s5 대체, s8 기준색 없음, s9 맞는 제품 없음 */
const MATCH = {
  matchId: "m1",
  guideId: GUIDE_ID,
  steps: [
    { stepId: "s2", result: "SAME", samePouchItemId: "same", noneReason: null, candidates: [] },
    {
      stepId: "s5",
      result: "SUBSTITUTE",
      samePouchItemId: null,
      noneReason: null,
      candidates: [{ pouchItemId: "tint", rank: 1 }],
    },
    {
      stepId: "s8",
      result: "NONE",
      samePouchItemId: null,
      noneReason: "COMPARISON_UNAVAILABLE",
      candidates: [],
    },
    {
      stepId: "s9",
      result: "NONE",
      samePouchItemId: null,
      noneReason: "NO_SUITABLE_ITEM",
      candidates: [],
    },
  ],
};

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
  vi.spyOn(api, "post").mockResolvedValue(MATCH);
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

const steps = () =>
  [...element.querySelectorAll("[data-step]")].map((e) => e.getAttribute("data-step"));
const tab = (label: string) => button(label, element.querySelector('[role="tablist"]')!);

describe("실제 가이드 제품 체크", () => {
  it("서버 매칭으로 보유·대체·없음을 나누고 없음부터 보여 준다", () => {
    expect(api.post).toHaveBeenCalledWith(
      "/v1/users/me/guide-matches",
      expect.objectContaining({ body: { guideId: GUIDE_ID } }),
    );
    expect(text()).toContain("2/4");
    expect(steps()).toEqual(["s8", "s9"]);
    expect(text()).toContain("영상 색 정보가 없음");
    expect(text()).toContain("파우치에 적절한 제품이 없음");
  });

  it("보유·대체 탭에 서버가 고른 내 제품을 보여 준다", async () => {
    await click(tab("보유"));
    expect(steps()).toEqual(["s2"]);
    expect(text()).toContain("→ 롬앤 베러 댄 치크");
    await click(tab("대체"));
    expect(steps()).toEqual(["s5"]);
    expect(text()).toContain("→ C 틴트");
  });

  it("없음 단계에서 고르면 대체로 옮기고, 선택 해제하면 서버 결과로 돌아간다", async () => {
    await click(button("선택", element.querySelector('[data-step="s8"]')!));
    await click(button("글로우"));
    expect(session.state.run.choice).toEqual({ s8: { kind: "pouch", id: "high" } });
    expect(text()).toContain("3/4");
    await click(tab("대체"));
    await click(button("바꾸기", element.querySelector('[data-step="s8"]')!));
    await click(button("선택 해제"));
    expect(session.state.run.choice).toEqual({});
    expect(text()).toContain("2/4");
  });

  it("시작하면 화면에 보이는 결과를 선택으로 저장하고 없음은 생략한다", async () => {
    await click(button("이 조합으로 시작"));
    expect(text()).toContain("없는 제품 2개는");
    await click(button("건너뛰고 시작"));
    expect(session.state.run.choice).toEqual({
      s2: { kind: "pouch", id: "same", auto: true },
      s5: { kind: "pouch", id: "tint", auto: true },
      s8: { kind: "none", auto: true },
      s9: { kind: "none", auto: true },
    });
    expect(router.push).toHaveBeenCalledWith(`/tutorial/guide?guideId=${GUIDE_ID}`);
  });

  it("직접 고른 단계는 그대로 두고, 자동 저장한 단계는 다시 맞추면 새 결과를 쓴다", async () => {
    await click(button("선택", element.querySelector('[data-step="s8"]')!));
    await click(button("글로우"));
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    expect(session.state.run.choice.s8).toEqual({ kind: "pouch", id: "high" });
    expect(session.state.run.choice.s9).toEqual({ kind: "none", auto: true });
    // 돌아와 제품을 등록하면 s9에도 대체 후보가 생긴다
    vi.mocked(api.post).mockResolvedValueOnce({
      ...MATCH,
      steps: MATCH.steps.map((s) =>
        s.stepId === "s9"
          ? {
              ...s,
              result: "SUBSTITUTE",
              noneReason: null,
              candidates: [{ pouchItemId: "tint", rank: 1 }],
            }
          : s,
      ),
    });
    await act(async () => {
      session.update({ pouch: [...pouch].map((p) => ({ ...p, brand: p.brand + " " })) });
    });
    await click(tab("대체"));
    expect(steps()).toContain("s9");
    expect(element.querySelector('[data-step="s9"]')?.textContent).not.toContain("제품 생략");
  });

  it("매칭에 실패하면 모두 없음으로 두고 다시 맞춰 볼 수 있다", async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error("down"));
    // 파우치가 바뀌면 다시 맞춘다
    await act(async () => {
      session.update({ pouch: pouch.filter((p) => p.id !== "high") });
    });
    expect(text()).toContain("다시 맞춰 보기");
    expect(text()).toContain("0/4");
    await click(button("다시 맞춰 보기"));
    expect(text()).toContain("2/4");
  });

  it("매칭에 실패한 동안은 시작할 수 없어 실패한 단계를 생략으로 저장하지 않는다", async () => {
    vi.mocked(api.post).mockRejectedValueOnce(new Error("down"));
    await act(async () => {
      session.update({ pouch: pouch.filter((p) => p.id !== "high") });
    });
    expect(button("이 조합으로 시작").disabled).toBe(true);
    await click(button("이 조합으로 시작"));
    expect(text()).not.toContain("없는 제품");
    expect(session.state.run.choice).toEqual({});
    await click(button("다시 맞춰 보기"));
    expect(button("이 조합으로 시작").disabled).toBe(false);
  });

  it("제품의 종류·호수·색을 고치면 ID가 같아도 다시 맞춘다", async () => {
    expect(api.post).toHaveBeenCalledTimes(1);
    await act(async () => {
      session.update({
        pouch: pouch.map((p) => (p.id === "high" ? { ...p, shade: "02", color: "#E8CBB0" } : p)),
      });
    });
    expect(api.post).toHaveBeenCalledTimes(2);
    await act(async () => {
      session.update({
        pouch: pouch.map((p) => (p.id === "high" ? { ...p, shade: "02", color: "#E8CBB0" } : p)),
      });
    });
    expect(api.post).toHaveBeenCalledTimes(2);
  });
});
