// @vitest-environment jsdom
import { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GuideModel, GuideStepModel } from "@/features/guide";
import { RunGuideContext } from "@/features/guide/use-guide";
import type { PouchItem } from "@/features/pouch";
import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api } from "@/lib/api";

import { GuideDone } from "./guide-done";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const step = (stepId: string, order: number): GuideStepModel => ({
  stepId,
  order,
  makeup: "blush",
  label: `단계 ${order}`,
  summary: null,
  actions: [],
  doneWhen: null,
  product: { name: "영상 제품", shade: null },
  matchCategory: "CHEEK",
  previewable: false,
  subSteps: [],
});
const guide: GuideModel = {
  guideId: GUIDE_ID,
  guideVersion: 2,
  videoId: "v",
  youtubeVideoId: "yt",
  thumbnailUrl: null,
  title: "실제 가이드",
  channelTitle: "채널",
  meshVersion: null,
  steps: [step("s2", 1), step("s5", 2), step("s8", 3)],
};
const pouch: PouchItem[] = [{ id: "p1", cat: "치크", brand: "클리오", name: "블러셔" }];

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
const button = (label: string) => {
  const found = [...element.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
  if (!found) throw new Error(`${label} 버튼이 없습니다`);
  return found;
};

async function mount(search = "") {
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  const render = (body: boolean) =>
    root.render(
      <SessionProvider seed={{ pouch, reports: [] }}>
        <Probe />
        <RunGuideContext.Provider
          value={{
            search,
            load: { status: "ready", guide, checking: false, error: null },
            retry: async () => true,
          }}
        >
          {body && <GuideDone />}
        </RunGuideContext.Provider>
      </SessionProvider>,
    );
  await act(async () => render(false));
  await act(async () => {
    // 로그인 확인 뒤 서버 파우치 목록을 받은 상태
    session.update({ pouch });
    session.startRun({ kind: "guide", guideId: GUIDE_ID });
  });
  const id = session.state.run.id;
  await act(async () => {
    session.bindGuide(id, 2, {
      id: "v",
      ytid: "yt",
      title: "실제 가이드",
      ch: "채널",
      meta: "",
      dur: "",
    });
    session.updateRun({ choice: { s2: { kind: "pouch", id: "p1" }, s5: { kind: "none" } } }, id);
    session.enterTutorial(id, true);
  });
  await act(async () => {
    session.updateRun({ captures: ["s2", "s8"] }, id);
    session.completeRun(id);
  });
  await act(async () => render(true));
}
const flush = async () => {
  await act(async () => vi.advanceTimersByTime(1200));
};

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  vi.useFakeTimers();
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
    clear: () => saved.clear(),
  });
  vi.clearAllMocks();
  vi.spyOn(api, "get").mockResolvedValue({ user: { email: "t@example.com" }, csrfToken: "c" });
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("실제 가이드 완료", () => {
  it("가이드 단계 수와 제목으로 완료를 보여 주고 샘플 사진을 쓰지 않는다", async () => {
    await mount();
    expect(text()).toContain("LOOK COMPLETE · 3 / 3");
    expect(text()).toContain("실제 가이드 · 완성했어요");
    expect(text()).toContain("마지막 단계 사진을 남겼어요");
    expect(element.querySelector("img")).toBeNull();
  });

  it("저장 성공 때 단계 스냅샷 기록을 남긴다", async () => {
    await mount();
    expect(session.state.reports).toHaveLength(0);
    await flush();
    const [report] = session.state.reports;
    expect(report).toMatchObject({
      id: `rp-${session.state.run.id}`,
      guideId: GUIDE_ID,
      guideVersion: 2,
      steps: 3,
      finalPhoto: true,
    });
    expect(report.guide?.steps.map((s) => [s.stepId, s.pick, s.photo])).toEqual([
      ["s2", "picked", true],
      ["s5", "skipped", false],
      ["s8", "undecided", true],
    ]);
  });

  it("저장에 실패하면 다시 시도로 실행 id 기록을 남긴다", async () => {
    await mount("fail=1");
    await flush();
    expect(text()).toContain("기록을 저장하지 못했어요");
    expect(session.state.reports).toHaveLength(0);
    await act(async () => button("다시 시도").click());
    await flush();
    expect(session.state.reports.map((r) => r.id)).toEqual([`rp-${session.state.run.id}`]);
  });

  it("리포트 보기는 저장 뒤에만 이동하고 실행은 직접 끝내지 않는다", async () => {
    await mount();
    await act(async () => button("리포트 보기").click());
    expect(router.replace).not.toHaveBeenCalled();
    await flush();
    const id = session.state.run.id;
    await act(async () => button("리포트 보기").click());
    expect(router.replace).toHaveBeenCalledWith(`/my/report?id=rp-${id}`);
    expect(session.state.run.id).toBe(id);
  });

  it("저장 전에 실행이 바뀌면 기록하지 않는다", async () => {
    await mount();
    await act(async () => {
      session.endRun(session.state.run.id);
    });
    await flush();
    expect(session.state.reports).toHaveLength(0);
    expect(text()).toContain("기록을 저장하지 못했어요");
    expect(text()).not.toContain("기록을 저장했어요");
  });
});
