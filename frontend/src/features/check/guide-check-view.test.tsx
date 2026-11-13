// @vitest-environment jsdom
import { act, useLayoutEffect, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveFacePhoto } from "@/features/face";
import type { GuideModel, GuideStepModel } from "@/features/guide";
import { RunGuideContext } from "@/features/guide/use-guide";
import type { PouchItem } from "@/features/pouch";
import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api, ApiError } from "@/lib/api";

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
  vi.spyOn(api, "get").mockImplementation(async (path: string) => {
    if (path === "/v1/users/me")
      return { user: { email: "t@example.com", nickname: "테스트" }, csrfToken: "c" };
    if (path === "/v1/users/me/pouch-items")
      return {
        items: pouch.map((item) => ({
          pouchItemId: item.id,
          registrationMode: "MANUAL",
          productId: null,
          shadeId: null,
          brand: item.brand,
          name: item.name,
          category: item.cat === "치크" ? "CHEEK" : "LIP",
          type: item.type,
          shadeName: null,
          color: item.color ? { hex: item.color, source: "USER_INPUT", estimated: false } : null,
          colorSource: item.color ? "USER_INPUT" : "NONE",
          createdAt: "2026-01-01T00:00:00Z",
          updatedAt: "2026-01-01T00:00:00Z",
        })),
        hasNext: false,
      };
    return { user: { email: "t@example.com" }, csrfToken: "c" };
  });
  // 매칭과 실행 시작
  vi.spyOn(api, "post").mockImplementation(async (path: string) =>
    path === "/v1/users/me/executions" ? { executionId: "e1" } : MATCH,
  );
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
  await act(async () => {
    // 로딩 화면에서 서버에 얼굴을 등록한 상태
    session.updateRun({ faceReg: true, faceRegistrationId: "f1" }, session.state.run.id);
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
  it("화면 진입 시 서버 파우치를 동기화하고 매칭 요청을 보낸다", () => {
    expect(api.get).toHaveBeenCalledWith(
      "/v1/users/me/pouch-items",
      expect.objectContaining({ query: { page: 0, size: 100 } }),
    );
    expect(session.state.pouch.map((item) => item.id)).toEqual(pouch.map((item) => item.id));
    expect(api.post).toHaveBeenCalledWith(
      "/v1/users/me/guide-matches",
      expect.objectContaining({ body: { guideId: GUIDE_ID } }),
    );
  });

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

  it("같은 카테고리의 다른 종류 제품도 직접 선택할 수 있다", async () => {
    await click(tab("보유"));
    await click(button("바꾸기", element.querySelector('[data-step="s2"]')!));
    await click(button("글로우"));
    expect(session.state.run.choice.s2).toEqual({ kind: "pouch", id: "high" });
    await click(tab("대체"));
    expect(element.querySelector('[data-step="s2"]')?.textContent).toContain("B 글로우");
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
    // 그 선택으로 서버 실행을 만들고, 받은 ID로 동의 화면에 간다
    expect(api.post).toHaveBeenCalledWith("/v1/users/me/executions", {
      body: {
        guideId: GUIDE_ID,
        matchId: "m1",
        faceRegistrationId: "f1",
        selections: [
          { stepId: "s2", selectedPouchItemId: "same" },
          { stepId: "s5", selectedPouchItemId: "tint" },
          { stepId: "s8", selectedPouchItemId: null },
          { stepId: "s9", selectedPouchItemId: null },
        ],
        acceptMissingProducts: true,
      },
    });
    expect(session.state.run.executionId).toBe("e1");
    expect(router.push).toHaveBeenCalledWith(`/tutorial/guide?guideId=${GUIDE_ID}`);
  });

  it("실행 생성 404인데 얼굴 등록이 남아 있으면 등록은 두고 다시 맞춰 안내한다", async () => {
    vi.mocked(api.post).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/executions") throw new ApiError(404, "NOT_FOUND", "없음");
      return MATCH;
    });
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    expect(api.get).toHaveBeenCalledWith("/v1/users/me/face-registrations/f1");
    expect(text()).toContain("가이드나 제품 매칭을 찾지 못해 다시 맞췄어요");
    expect(session.state.run.faceRegistrationId).toBe("f1");
  });

  it("실행 생성 404의 원인이 사라진 얼굴 등록이면 등록을 지워 다시 등록하게 한다", async () => {
    vi.mocked(api.post).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/executions") throw new ApiError(404, "NOT_FOUND", "없음");
      return MATCH;
    });
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path.startsWith("/v1/users/me/face-registrations/"))
        throw new ApiError(404, "NOT_FOUND", "없음");
      return { user: { email: "t@example.com" }, csrfToken: "c" };
    });
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    expect(session.state.run.faceRegistrationId).toBeNull();
    expect(router.push).not.toHaveBeenCalled();
  });

  it("이 얼굴로 만든 실행과 선택이 다르면 같은 사진으로 새로 등록해 새 실행을 만든다", async () => {
    saveFacePhoto(session.state.run.id, new Blob(["jpeg"], { type: "image/jpeg" }));
    let creates = 0;
    vi.mocked(api.post).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/executions") {
        creates += 1;
        if (creates === 1) throw new ApiError(409, "FACE_REGISTRATION_ALREADY_USED", "이미 사용");
        return { executionId: "e2" };
      }
      if (path === "/v1/users/me/face-registrations") return { faceRegistrationId: "f2" };
      return MATCH;
    });
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/face-registrations/f1") return { executionId: "e1" };
      if (path === "/v1/users/me/executions/e1")
        return { executionId: "e1", status: "IN_PROGRESS", steps: [] };
      return { user: { email: "t@example.com" }, csrfToken: "c" };
    });
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    expect(session.state.run).toMatchObject({ faceRegistrationId: "f2", executionId: "e2" });
    expect(router.push).toHaveBeenCalledWith(`/tutorial/guide?guideId=${GUIDE_ID}`);
  });

  it("새로 등록한 뒤 실행 생성이 404면 새 등록으로 원인을 가리고 새 등록을 남긴다", async () => {
    saveFacePhoto(session.state.run.id, new Blob(["jpeg"], { type: "image/jpeg" }));
    let creates = 0;
    vi.mocked(api.post).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/executions") {
        creates += 1;
        if (creates === 1) throw new ApiError(409, "FACE_REGISTRATION_ALREADY_USED", "이미 사용");
        throw new ApiError(404, "NOT_FOUND", "없음");
      }
      if (path === "/v1/users/me/face-registrations") return { faceRegistrationId: "f2" };
      return MATCH;
    });
    // 옛 등록(f1)은 처음 조회 때 기존 실행을 주고, 새로 등록한 뒤에는 사라진다
    let f1Reads = 0;
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/face-registrations/f1") {
        f1Reads += 1;
        if (f1Reads === 1) return { executionId: "e1" };
        throw new ApiError(404, "NOT_FOUND", "없음");
      }
      if (path === "/v1/users/me/executions/e1")
        return { executionId: "e1", status: "IN_PROGRESS", steps: [] };
      if (path === "/v1/users/me/face-registrations/f2") return { executionId: null };
      return { user: { email: "t@example.com" }, csrfToken: "c" };
    });
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    expect(api.get).toHaveBeenCalledWith("/v1/users/me/face-registrations/f2");
    expect(session.state.run.faceRegistrationId).toBe("f2");
    expect(text()).toContain("가이드나 제품 매칭을 찾지 못해 다시 맞췄어요");
  });

  it("실행 생성 응답을 기다리는 사이 실행이 끝나면 화면을 옮기지 않는다", async () => {
    let answer: (v: unknown) => void = () => {};
    vi.mocked(api.post).mockImplementation((path: string) =>
      path === "/v1/users/me/executions"
        ? new Promise((resolve) => (answer = resolve))
        : Promise.resolve(MATCH),
    );
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    await act(async () => {
      session.endRun(session.state.run.id);
    });
    await act(async () => answer({ executionId: "late" }));
    expect(router.push).not.toHaveBeenCalled();
    expect(session.state.run.executionId).toBeNull();
  });

  it("매칭이 낡았으면(409) 다시 맞추고 시작 창에 안내한다", async () => {
    vi.mocked(api.post).mockImplementation(async (path: string) => {
      if (path === "/v1/users/me/executions")
        throw new ApiError(409, "GUIDE_MATCH_STALE", "매칭이 바뀜");
      return MATCH;
    });
    await click(button("이 조합으로 시작"));
    await click(button("건너뛰고 시작"));
    expect(text()).toContain("제품 정보가 바뀌어 다시 맞췄어요");
    expect(router.push).not.toHaveBeenCalled();
    expect(session.state.run.executionId).toBeNull();
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
