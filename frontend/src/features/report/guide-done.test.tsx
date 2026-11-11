// @vitest-environment jsdom
import { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";

import type { GuideModel, GuideStepModel } from "@/features/guide";
import { RunGuideContext } from "@/features/guide/use-guide";
import type { PouchItem } from "@/features/pouch";
import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api } from "@/lib/api";

import { GuideDone } from "./guide-done";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const EXECUTION_ID = "e0000000-0000-4000-8000-000000000001";
const RECORD_ID = "r0000000-0000-4000-8000-000000000001";
const COMPLETION = `/v1/users/me/executions/${EXECUTION_ID}/completion`;
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
    session.updateRun(
      {
        choice: { s2: { kind: "pouch", id: "p1" }, s5: { kind: "none" } },
        executionId: EXECUTION_ID,
      },
      id,
    );
    session.enterTutorial(id, true);
  });
  await act(async () => {
    session.updateRun({ captures: ["s2", "s8"] }, id);
    session.completeRun(id);
  });
  await act(async () => render(true));
}
/** 완료 응답을 받고 화면이 갱신될 때까지 */
const flush = async () => {
  await act(async () => {
    await vi.runAllTimersAsync();
  });
};
/** 완료 요청. 기본은 바로 recordId를 준다 */
let post: MockInstance<typeof api.post>;

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
  post = vi.spyOn(api, "post").mockResolvedValue({
    executionId: EXECUTION_ID,
    status: "COMPLETED",
    recordId: RECORD_ID,
    completedAt: "2026-11-11T00:00:00Z",
  });
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

  it("서버 실행을 완료하고 받은 recordId로 단계 스냅샷 기록을 남긴다", async () => {
    await mount();
    await flush();
    expect(post).toHaveBeenCalledWith(COMPLETION);
    const [report] = session.state.reports;
    expect(report).toMatchObject({
      id: RECORD_ID,
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

  it("저장에 실패하면 다시 시도가 같은 실행으로 완료를 다시 보낸다", async () => {
    post.mockRejectedValueOnce(new Error("network"));
    await mount();
    await flush();
    expect(text()).toContain("기록을 저장하지 못했어요");
    expect(session.state.reports).toHaveLength(0);
    await act(async () => button("다시 시도").click());
    await flush();
    expect(post).toHaveBeenNthCalledWith(2, COMPLETION);
    expect(session.state.reports.map((r) => r.id)).toEqual([RECORD_ID]);
  });

  it("?fail=1은 첫 저장을 보내지 않고 실패로 보여 준다", async () => {
    await mount("fail=1");
    await flush();
    expect(post).not.toHaveBeenCalled();
    expect(text()).toContain("기록을 저장하지 못했어요");
  });

  it("리포트 보기는 저장 뒤에만 이동하고 실행은 직접 끝내지 않는다", async () => {
    let answer: (v: unknown) => void = () => {};
    post.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    await mount();
    await act(async () => button("리포트 보기").click());
    expect(router.replace).not.toHaveBeenCalled();
    await act(async () => answer({ recordId: RECORD_ID }));
    await flush();
    const id = session.state.run.id;
    await act(async () => button("리포트 보기").click());
    expect(router.replace).toHaveBeenCalledWith(`/my/report?id=${RECORD_ID}`);
    expect(session.state.run.id).toBe(id);
  });

  it("완료 응답 전에 실행이 바뀌면 기록하지 않는다", async () => {
    let answer: (v: unknown) => void = () => {};
    post.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    await mount();
    await act(async () => {
      session.endRun(session.state.run.id);
    });
    await act(async () => answer({ recordId: RECORD_ID }));
    await flush();
    expect(session.state.reports).toHaveLength(0);
    expect(text()).toContain("기록을 저장하지 못했어요");
    expect(text()).not.toContain("기록을 저장했어요");
  });
});
