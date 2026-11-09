// @vitest-environment jsdom
import { act, useLayoutEffect, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GuideModel, GuideStepModel } from "@/features/guide";
import { RunGuideContext } from "@/features/guide/use-guide";
import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api } from "@/lib/api";

import { GuidePreview } from "./guide-preview";
import { previewSummary } from "./preview-summary";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
const live = vi.hoisted(() => ({
  state: { note: null, reason: null, canRender: true } as {
    note: { title: string; desc: string; live: boolean; face: boolean } | null;
    reason: string | null;
    canRender: boolean;
  },
}));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/features/live", () => ({
  GlassPanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LiveTag: () => null,
  LiveNote: ({ note }: { note: { title: string; desc: string } | null }) =>
    note && (
      <p>
        {note.title} {note.desc}
      </p>
    ),
  parseAlert: () => null,
  RoundBack: ({ onClick, label }: { onClick: () => void; label: string }) => (
    <button type="button" onClick={onClick}>
      {label}
    </button>
  ),
  useLiveState: () => live.state,
}));

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const step = (
  stepId: string,
  makeup: GuideStepModel["makeup"],
  previewable: boolean,
): GuideStepModel => ({
  stepId,
  order: Number(stepId.slice(1)),
  makeup,
  label: `${makeup} 단계`,
  summary: null,
  actions: [],
  doneWhen: null,
  product: null,
  matchCategory: null,
  previewable,
  subSteps: [],
});
const guide = (steps: GuideStepModel[]): GuideModel => ({
  guideId: GUIDE_ID,
  guideVersion: 1,
  videoId: "v",
  youtubeVideoId: null,
  thumbnailUrl: null,
  title: "실제 가이드",
  channelTitle: "채널",
  meshVersion: null,
  steps,
});
const STEPS = [
  step("s1", "foundation", false),
  step("s2", "eyeshadow", true),
  step("s3", "eyeshadow", true),
  step("s4", "mascara", false),
  step("s5", "lip", true),
];

describe("previewSummary", () => {
  it("대상 단계 수와 화장 종류를 중복 없이 센다", () => {
    expect(previewSummary(guide(STEPS))).toEqual({
      targets: 3,
      total: 5,
      kinds: ["아이섀도", "립"],
      excluded: ["베이스", "마스카라"],
    });
  });
  it("일부 단계만 대상인 화장 종류는 제외 목록에 넣지 않는다", () => {
    const mixed = [...STEPS, step("s6", "eyeshadow", false)];
    expect(previewSummary(guide(mixed))).toMatchObject({
      targets: 3,
      total: 6,
      kinds: ["아이섀도", "립"],
      excluded: ["베이스", "마스카라"],
    });
  });
});

let root: Root;
let element: HTMLDivElement;
let session: ReturnType<typeof useSession>;
function Probe() {
  const value = useSession();
  useLayoutEffect(() => {
    session = value;
  });
  return null;
}
const text = () => element.textContent ?? "";

async function mount(steps: GuideStepModel[]) {
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  await act(async () =>
    root.render(
      <SessionProvider seed={{ pouch: [], reports: [] }}>
        <Probe />
        <RunGuideContext.Provider
          value={{
            search: "",
            load: { status: "ready", guide: guide(steps), checking: false, error: null },
            retry: async () => true,
          }}
        >
          <GuidePreview />
        </RunGuideContext.Provider>
      </SessionProvider>,
    ),
  );
  await act(async () => session.startRun({ kind: "guide", guideId: GUIDE_ID }));
}

describe("실제 가이드 미리보기", () => {
  beforeEach(() => {
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
    const saved = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => saved.get(key) ?? null,
      setItem: (key: string, value: string) => saved.set(key, value),
      clear: () => saved.clear(),
    });
    vi.clearAllMocks();
    live.state = { note: null, reason: null, canRender: true };
    vi.spyOn(api, "get").mockResolvedValue({ user: { email: "t@example.com" }, csrfToken: "c" });
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    element.remove();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("대상 단계와 색상 미제공을 안내하고 입혀보는 중이라고 하지 않는다", async () => {
    await mount(STEPS);
    expect(text()).toContain("미리보기 대상 3 / 전체 5단계 · 아이섀도 · 립");
    expect(text()).toContain("색 비교가 어려운 베이스 · 마스카라 단계는 빠져요");
    expect(text()).toContain("색상 정보가 없어");
    expect(text()).not.toMatch(/입혀보는 중|입혀 볼게요|민낯으로 보기/);
  });

  it.each([
    ["lost", "화면 가운데로 돌아오면 메이크업이 다시 보여요.", "화면 가운데로 돌아와 주세요."],
    ["cover", "가린 동안 메이크업을 잠시 숨겼어요.", "얼굴 전체가 보이게 해 주세요."],
  ])("인식 알림(%s)은 숨김 대신 할 일만 안내한다", async (reason, desc, plain) => {
    live.state = {
      note: { title: "알림", desc, live: true, face: true },
      reason,
      canRender: false,
    };
    await mount(STEPS);
    expect(text()).toContain(`알림 ${plain}`);
    expect(text()).not.toMatch(/메이크업|숨겼/);
  });

  it.each([
    ["error", "카메라를 쓸 수 없어요", "브라우저 설정에서 카메라를 허용해 주세요."],
    ["starting", "카메라를 켜는 중이에요", "잠시만 기다려 주세요."],
  ])("카메라 상태 안내(%s)는 문구를 바꾸지 않는다", async (reason, title, desc) => {
    live.state = { note: { title, desc, live: false, face: false }, reason, canRender: false };
    await mount(STEPS);
    expect(text()).toContain(`${title} ${desc}`);
  });

  it("대상이 없으면 그렇게 알린다", async () => {
    await mount([step("s1", "foundation", false)]);
    expect(text()).toContain("미리볼 수 있는 단계가 없어요");
  });

  it("시작은 같은 가이드의 제품 체크로, 뒤로는 영상 목록으로 간다", async () => {
    await mount(STEPS);
    const button = (label: string) =>
      [...element.querySelectorAll("button")].find((b) => b.textContent?.includes(label))!;
    await act(async () => button("이 가이드로 단계 안내 시작").click());
    expect(router.push).toHaveBeenCalledWith(`/check?guideId=${GUIDE_ID}`);
    await act(async () => button("영상 목록으로").click());
    expect(router.push).toHaveBeenLastCalledWith("/select");
  });
});
