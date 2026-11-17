// @vitest-environment jsdom
import { act, StrictMode, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TutorialGuidePage from "@/app/(live)/(camera)/tutorial/guide/page";
import { clearFacePhoto, facePhoto, saveFacePhoto } from "@/features/face/registered-photo";
import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api, ApiError } from "@/lib/api";

import { RunGuideProvider } from "./run-guide-provider";
import { useGuide } from "./use-guide";

const nav = vi.hoisted(() => ({
  path: "/loading",
  search: "",
  router: { push: vi.fn(), replace: vi.fn() },
}));
const fetch = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  usePathname: () => nav.path,
  useSearchParams: () => new URLSearchParams(nav.search),
  useRouter: () => nav.router,
}));
vi.mock("./guide-api", () => ({ fetchGuide: fetch }));
vi.mock("@/features/face", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/face")>()),
  useHiddenVideo: () => {},
}));
vi.mock("@/features/live", () => ({ CameraErrorNote: () => null }));

const A = "a0000000-0000-4000-8000-000000000001";
const B = "a0000000-0000-4000-8000-000000000002";
const raw = (guideId = A) => ({
  guideId,
  guideVersion: 1,
  videoId: "video",
  title: "실제 가이드",
  stepCount: 13,
  steps: Array.from({ length: 13 }, (_, i) => ({
    stepId: `s${i}`,
    order: i + 1,
    type: "GUIDE",
    part: "blush",
  })),
});

let session: ReturnType<typeof useSession>;
let guide: ReturnType<typeof useGuide>;
let root: Root;
let element: HTMLDivElement;
let realConsent = false;
function SessionProbe() {
  const value = useSession();
  useLayoutEffect(() => {
    session = value;
  });
  return null;
}
/** 본문이 그려질 때의 주소 쿼리와 실행 가이드 */
const bodyRenders: string[] = [];
function Body() {
  const value = useGuide();
  const { state } = useSession();
  bodyRenders.push(`${nav.search}|${state.run.guideId}`);
  useLayoutEffect(() => {
    guide = value;
  });
  return (
    <div data-testid="body">
      {value.load.status === "ready" ? value.load.guide.steps.length : "sample"}
    </div>
  );
}
function Frame() {
  return (
    <StrictMode>
      <SessionProvider>
        <SessionProbe />
        <RunGuideProvider>
          {realConsent && nav.path === "/tutorial/guide" ? (
            <TutorialGuidePage />
          ) : (
            <Body key={nav.path} />
          )}
        </RunGuideProvider>
      </SessionProvider>
    </StrictMode>
  );
}
async function navigate(url: string) {
  const [path, search = ""] = url.split("?");
  nav.path = path;
  nav.search = search;
  await act(async () => {
    root.render(<Frame />);
  });
}
async function registerFace() {
  await act(async () => {
    saveFacePhoto(session.state.run.id, new Blob());
    // 서버 얼굴 등록 · 제품 체크의 실행 시작까지 마친 상태
    session.updateRun(
      { faceReg: true, faceRegistrationId: "f1", executionId: "e1" },
      session.state.run.id,
    );
  });
}
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  // Node의 전역 저장소 대신 테스트마다 분리된 브라우저 저장소 대역을 쓴다.
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => {
      saved.set(key, value);
    },
    clear: () => saved.clear(),
  });
  localStorage.clear();
  clearFacePhoto();
  vi.clearAllMocks();
  vi.spyOn(api, "get").mockResolvedValue({
    user: { email: "test@example.com", nickname: "테스트" },
    csrfToken: "csrf",
  });
  fetch.mockReset().mockImplementation(async (id: string) => raw(id));
  // 사진 동의
  vi.spyOn(api, "patch").mockResolvedValue({ photoConsent: true });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  nav.path = "/loading";
  nav.search = `guideId=${A}`;
  realConsent = false;
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("루트 실행·가이드 연동", () => {
  it("같은 분석 결과로 이동하면 촬영 사진과 준비 상태를 이어 쓴다", async () => {
    await navigate("/loading?jobId=j1");
    await act(async () => session.startRun({ kind: "sample", jobId: "j1" }));
    const id = session.state.run.id;
    const photo = new Blob(["face"]);
    await act(async () => {
      saveFacePhoto(id, photo);
      session.updateRun(
        { faceReg: true, faceRegistrationId: "f1", facePrompted: true, pouchReviewed: true },
        id,
      );
    });
    await navigate(`/loading?guideId=${B}&jobId=j1`);
    expect(session.state.run).toMatchObject({
      id,
      mode: "guide",
      guideId: B,
      faceReg: true,
      facePrompted: true,
      pouchReviewed: true,
      faceRegistrationId: "f1",
    });
    expect(facePhoto(id)).toBe(photo);
    expect(nav.router.replace).toHaveBeenLastCalledWith(`/loading?guideId=${B}`);
  });

  it("다른 분석의 결과로 이동하면 이전 사진과 준비 상태를 버린다", async () => {
    const remove = vi.spyOn(api, "delete").mockResolvedValue(undefined);
    await navigate("/loading?jobId=j1");
    await act(async () => session.startRun({ kind: "sample", jobId: "j1" }));
    const id = session.state.run.id;
    await act(async () => {
      saveFacePhoto(id, new Blob());
      session.updateRun(
        { faceReg: true, faceRegistrationId: "old-face", facePrompted: true, pouchReviewed: true },
        id,
      );
    });
    await navigate(`/loading?guideId=${B}&jobId=j2`);
    expect(session.state.run.id).not.toBe(id);
    expect(session.state.run).toMatchObject({
      faceReg: false,
      facePrompted: false,
      pouchReviewed: false,
    });
    expect(facePhoto(id)).toBeNull();
    expect(remove).toHaveBeenCalledWith("/v1/users/me/face-registrations/old-face");
  });

  it("분석 화면에서 나가면 실행에 연결하지 않은 서버 얼굴 등록을 정리한다", async () => {
    const remove = vi.spyOn(api, "delete").mockResolvedValue(undefined);
    await navigate("/loading?jobId=j1");
    await act(async () => session.startRun({ kind: "sample", jobId: "j1" }));
    const id = session.state.run.id;
    await act(async () => {
      saveFacePhoto(id, new Blob());
      session.updateRun({ faceReg: true, faceRegistrationId: "analysis-face" }, id);
    });
    await navigate("/select");
    expect(remove).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledWith("/v1/users/me/face-registrations/analysis-face");
    expect(session.state.run.id).toBe("");
    expect(facePhoto(id)).toBeNull();
  });

  it("StrictMode에서도 URL로 한 실행을 만들고 화면 전환에서는 재조회하지 않는다", async () => {
    await navigate(`/loading?guideId=${A}`);
    const firstId = session.state.run.id;
    expect(firstId).not.toBe("");
    expect(session.state.run).toMatchObject({
      guideId: A,
      guideVersion: 1,
      photoOk: false,
      faceReg: false,
    });
    expect(element.textContent).toBe("13");
    expect(fetch).toHaveBeenCalledTimes(1);
    await registerFace();
    await navigate(`/tutorial/guide?guideId=${A}`);
    expect(session.state.run.id).toBe(firstId);
    expect(element.textContent).toBe("13");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("같은 경로에서 guideId 쿼리만 바뀌어도 새 실행으로 전환한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    const old = session.state.run.id;
    bodyRenders.length = 0;
    await navigate(`/loading?guideId=${B}`);
    // 바뀐 주소로 이전 실행의 본문을 그리지 않는다
    expect(bodyRenders).not.toContain(`guideId=${B}|${A}`);
    expect(session.state.run.id).not.toBe(old);
    expect(session.state.run.guideId).toBe(B);
    expect(fetch).toHaveBeenLastCalledWith(B, expect.any(AbortSignal));
  });
  it("같은 가이드 재실행은 동의·사진·선택을 초기화하고 새로 조회한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    const old = session.state.run.id;
    await act(async () => {
      session.updateRun({ photoOk: true, captures: ["s1"], choice: { s1: { kind: "none" } } });
    });
    await act(async () => {
      session.startRun({ kind: "guide", guideId: A });
      expect(session.isCurrentRun(old)).toBe(false);
    });
    expect(session.state.run).toMatchObject({
      photoOk: false,
      faceReg: false,
      guideVersion: 1,
      choice: {},
      captures: [],
    });
    expect(session.state.run.id).not.toBe(old);
    expect(facePhoto(old)).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("실제 안내 문구는 공유 가이드의 13단계로 계산하고 동의 전 재검증한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    const id = session.state.run.id;
    await act(async () => {
      session.update({ tutSeen: true });
    });
    realConsent = true;
    await navigate(`/tutorial/guide?guideId=${A}`);
    expect(document.body.textContent).toContain("최대 13장");
    const button = [...document.querySelectorAll("button")].find(
      (b) => b.textContent === "동의하고 시작",
    )!;
    expect(button).toBeTruthy();
    await act(async () => {
      button.click();
    });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(api.patch).toHaveBeenCalledWith("/v1/users/me/executions/e1/photo-consent", {
      body: { enabled: true },
    });
    expect(session.state.run).toMatchObject({ id, phase: "tutorial", photoOk: true });
    expect(nav.router.push).toHaveBeenCalledWith(`/tutorial?guideId=${A}`);
  });
  it("동의 카드의 돌아가기는 같은 가이드의 제품 체크로 간다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => {
      session.update({ tutSeen: true });
    });
    realConsent = true;
    await navigate(`/tutorial/guide?guideId=${A}`);
    const back = [...document.querySelectorAll("button")].find(
      (b) => b.textContent === "돌아가기",
    )!;
    await act(async () => {
      back.click();
    });
    expect(nav.router.push).toHaveBeenCalledWith(`/check?guideId=${A}`);
    expect(session.state.run).toMatchObject({ phase: "preparing", photoOk: false });
  });
  it("같은 안내 경로의 review 쿼리 변경을 읽고 돌아갈 때 동의·진행을 유지한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => {
      session.update({ tutSeen: true });
      session.enterTutorial(session.state.run.id, true);
    });
    realConsent = true;
    await navigate(`/tutorial/guide?guideId=${A}`);
    expect(document.body.textContent).toContain("최대 13장");
    await navigate(`/tutorial/guide?guideId=${A}&review=1`);
    expect(document.body.textContent).not.toContain("최대 13장");
    const skip = [...document.querySelectorAll("button")].find(
      (b) => b.textContent === "건너뛰기",
    )!;
    await act(async () => {
      skip.click();
    });
    expect(nav.router.push).toHaveBeenCalledWith(`/tutorial?guideId=${A}`);
    expect(session.state.run).toMatchObject({ phase: "tutorial", photoOk: true });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("동의 재검증 도중 가이드를 바꾸면 이전 동의가 새 실행에 반영되지 않는다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => {
      session.update({ tutSeen: true });
    });
    realConsent = true;
    await navigate(`/tutorial/guide?guideId=${A}`);
    let finish!: (value: unknown) => void;
    fetch.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const save = [...document.querySelectorAll("button")].find(
      (b) => b.textContent === "동의하고 시작",
    )!;
    await act(async () => {
      save.click();
      save.click();
    });
    expect(fetch).toHaveBeenCalledTimes(2);
    await navigate(`/loading?guideId=${B}`);
    await act(async () => {
      finish(raw(A));
    });
    expect(session.state.run).toMatchObject({ guideId: B, phase: "preparing", photoOk: false });
    expect(nav.router.push).not.toHaveBeenCalledWith(`/tutorial?guideId=${A}`);
  });
  it("저장된 옛 run을 버리고 리포트·파우치를 유지하며 run은 다시 저장하지 않는다", async () => {
    localStorage.setItem(
      "mairor-session-v2",
      JSON.stringify({
        loggedIn: true,
        email: "test@example.com",
        reports: [{ id: "old-report" }],
        pouch: [{ id: "old-pouch" }],
        run: { id: "old", photoOk: true, faceReg: true, captures: ["s1"] },
      }),
    );
    await navigate(`/loading?guideId=${A}`);
    expect(session.state.run).toMatchObject({
      photoOk: false,
      faceReg: false,
      captures: [],
      choice: {},
    });
    expect(session.state.run.id).not.toBe("old");
    expect(session.state.reports[0].id).toBe("old-report");
    expect(session.state.pouch[0].id).toBe("old-pouch");
    expect(JSON.parse(localStorage.getItem("mairor-session-v2")!)).not.toHaveProperty("run");
  });
  it.each(["/tutorial", "/done"])(
    "%s 직접 진입은 본문 부작용보다 먼저 얼굴 등록으로 보낸다",
    async (path) => {
      await navigate(`${path}?guideId=${A}`);
      expect(nav.router.replace).toHaveBeenCalledWith(`/loading?guideId=${A}`);
      expect(element.querySelector('[data-testid="body"]')).toBeNull();
      expect(session.state.reports).toHaveLength(0);
    },
  );
  it("실행 교체 후 이전 갱신·종료가 새 실행과 새 등록 사진을 지우지 않는다", async () => {
    await navigate(`/loading?guideId=${A}`);
    const oldId = session.state.run.id;
    await act(async () => {
      session.startRun({ kind: "guide", guideId: B });
    });
    // URL도 같은 새 실행을 가리키게 한다.
    await navigate(`/loading?guideId=${B}`);
    const newId = session.state.run.id;
    await registerFace();
    await act(async () => {
      session.updateRun({ photoOk: true, captures: ["s2"] }, oldId);
      session.enterTutorial(oldId, true);
      session.completeRun(oldId);
      session.endRun(oldId);
    });
    expect(session.state.run).toMatchObject({
      id: newId,
      guideId: B,
      faceReg: true,
      photoOk: false,
      captures: [],
    });
    expect(facePhoto(newId)).not.toBeNull();
  });
  it("재조회 404는 동의·사진·선택을 버리고 가이드를 무효화한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => {
      session.updateRun({ photoOk: true, captures: ["s2"], choice: { s1: { kind: "none" } } });
    });
    fetch.mockRejectedValueOnce(new ApiError(404, "NOT_FOUND", "없음"));
    await act(async () => {
      await guide.retry();
    });
    expect(session.state.run).toMatchObject({
      phase: "invalidated",
      photoOk: false,
      faceReg: false,
      captures: [],
      choice: {},
    });
    expect(facePhoto(session.state.run.id)).toBeNull();
    expect(element.textContent).toContain("처음부터 시작");
  });
  it("401이면 실행과 사진을 해제하고 다시 자동 시작하지 않는다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    fetch.mockRejectedValueOnce(new ApiError(401, "UNAUTHORIZED", "로그인 필요"));
    await act(async () => {
      await guide.retry();
    });
    expect(session.state.loggedIn).toBe(false);
    expect(session.state.sessionExpired).toBe(true);
    expect(session.state.run.id).toBe("");
    expect(nav.router.replace).toHaveBeenLastCalledWith("/login?expired=basic");
  });
  it("튜토리얼 중 401이면 기록 없이 종료됐다고 안내한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => session.enterTutorial(session.state.run.id, false));
    fetch.mockRejectedValueOnce(new ApiError(401, "UNAUTHORIZED", "로그인 필요"));
    await act(async () => {
      await guide.retry();
    });
    expect(session.state.sessionExpired).toBe(true);
    expect(nav.router.replace).toHaveBeenLastCalledWith("/login?expired=tut");
  });
  it("완료한 실행은 얼굴 사진이 없어도 완료 화면에 머문다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => {
      const id = session.state.run.id;
      session.enterTutorial(id, false);
      session.completeRun(id);
    });
    await navigate(`/done?guideId=${A}`);
    nav.router.replace.mockClear();
    clearFacePhoto();
    await navigate(`/done?guideId=${A}`);
    expect(nav.router.replace).not.toHaveBeenCalled();
    expect(element.textContent).not.toContain("얼굴을 다시 등록해 주세요");
  });
  it("샘플 실행을 끝낸 직후 남은 주소에서 영상 입력으로 보내지 않는다", async () => {
    await navigate("/home");
    await act(async () => session.startRun({ kind: "sample" }));
    await navigate("/done");
    expect(session.state.run.mode).toBe("sample");
    nav.router.replace.mockClear();
    await act(async () => session.endRun(session.state.run.id));
    expect(nav.router.replace).not.toHaveBeenCalledWith("/select");
  });
  it("실행을 종료하는 순간 현재 URL이 잠시 남아 있어도 실행을 되살리지 않는다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await act(async () => {
      session.endRun(session.state.run.id);
    });
    expect(session.state.run.id).toBe("");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("제품 확인은 같은 실행의 가이드로 본문을 연다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await navigate(`/check?guideId=${A}`);
    expect(element.querySelector('[data-testid="body"]')?.textContent).toBe("13");
  });
  it("완료는 같은 실행의 가이드로 본문을 연다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    await act(async () => {
      const id = session.state.run.id;
      session.enterTutorial(id, false);
      session.completeRun(id);
    });
    await navigate(`/done?guideId=${A}`);
    expect(element.querySelector('[data-testid="body"]')?.textContent).toBe("13");
  });
  it("완료 후 실행 밖으로 나가면 실행을 해제하고 같은 가이드로 다시 들어오면 새로 시작한다", async () => {
    await navigate(`/loading?guideId=${A}`);
    await registerFace();
    const done = session.state.run.id;
    await act(async () => {
      session.enterTutorial(done, false);
      session.completeRun(done);
    });
    await navigate(`/done?guideId=${A}`);
    await navigate("/my/reports");
    expect(session.state.run.id).toBe("");
    nav.router.replace.mockClear();
    await navigate(`/loading?guideId=${A}`);
    expect(session.state.run.id).not.toBe("");
    expect(session.state.run.id).not.toBe(done);
    expect(session.state.run.phase).toBe("preparing");
    expect(nav.router.replace).not.toHaveBeenCalledWith(expect.stringContaining("/done"));
  });
});
