// @vitest-environment jsdom
import { act, StrictMode, useLayoutEffect, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoadingPage from "@/app/(live)/loading/page";
import { clearFacePhoto, facePhoto, saveFacePhoto } from "@/features/face/registered-photo";
import { SessionProvider, useSession } from "@/features/session";
import { api, ApiError, type AnalysisJobStatus } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  query: new URLSearchParams("jobId=j1"),
  router: { push: vi.fn(), replace: vi.fn() },
  stop: vi.fn(),
  register: vi.fn(),
  remove: vi.fn(),
  retry: vi.fn(),
  live: {
    job: null as AnalysisJobStatus | null,
    pct: 0,
    error: null as ApiError | null,
    restart: vi.fn(),
  },
}));
const GUIDE = "a0000000-0000-4000-8000-000000000001";
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/features/face", async (original) => ({
  ...(await original<typeof import("@/features/face")>()),
  useCamera: () => ({ stop: mocks.stop }),
  useHiddenVideo: () => {},
}));
vi.mock("@/features/guide", async (original) => ({
  ...(await original<typeof import("@/features/guide")>()),
  useRunQuery: () => mocks.query,
  useGuide: () => ({
    load: { status: "ready", guide: { videoId: "v", guideId: GUIDE, steps: [] } },
  }),
  registerFace: mocks.register,
  deleteFaceRegistration: mocks.remove,
}));
vi.mock("@/features/loading", async (original) => ({
  ...(await original<typeof import("@/features/loading")>()),
  useAnalysisJob: () => mocks.live,
  retryAnalysisJob: mocks.retry,
  AnalysisProgress: ({ pct }: { pct: number }) => <output data-testid="progress">{pct}</output>,
  FoundProducts: () => null,
  ScanPreview: () => null,
  ReadyStatus: () => null,
  FaceRegisterModal: function MockFaceRegisterModal({
    onDone,
    onLater,
    runId,
  }: {
    onDone: () => Promise<void>;
    onLater: () => void;
    runId: string;
  }) {
    const [error, setError] = useState("");
    return (
      <div data-testid="face">
        {error && <p role="alert">{error}</p>}
        <button
          onClick={async () => {
            if (!facePhoto(runId)) saveFacePhoto(runId, new Blob(["face"]));
            try {
              await onDone();
            } catch (e) {
              setError(String(e));
            }
          }}
        >
          촬영 완료
        </button>
        <button onClick={onLater}>나중에</button>
      </div>
    );
  },
  PouchCheckModal: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="pouch">
        <button onClick={onClose}>파우치 확인 완료</button>
      </div>
    ) : null,
}));

const job = (over: Partial<AnalysisJobStatus> = {}): AnalysisJobStatus => ({
  jobId: "j1",
  videoId: "v",
  status: "PENDING",
  progressStage: "QUEUED",
  progressPercent: null,
  estimatedRemainingSeconds: null,
  stageProgress: null,
  retryable: false,
  reviewStatus: "NOT_READY",
  guideAvailable: false,
  guideId: null,
  foundProducts: [],
  foundProductCount: 0,
  totalProductCount: null,
  failureCode: null,
  failureMessage: null,
  pollAfterSeconds: 3,
  createdAt: "2026-11-12T00:00:00Z",
  completedAt: null,
  ...over,
});
let root: Root;
let element: HTMLDivElement;
let session: ReturnType<typeof useSession>;
let show = false;
function Probe() {
  const value = useSession();
  useLayoutEffect(() => {
    session = value;
  });
  return null;
}
function Frame() {
  return (
    <StrictMode>
      <SessionProvider>
        <Probe />
        {show && <LoadingPage />}
      </SessionProvider>
    </StrictMode>
  );
}
async function render() {
  await act(async () => root.render(<Frame />));
}
async function mount(guide = false, captured = false) {
  await render();
  await act(async () =>
    session.startRun(guide ? { kind: "guide", guideId: GUIDE } : { kind: "sample", jobId: "j1" }),
  );
  if (captured)
    await act(async () => {
      saveFacePhoto(session.state.run.id, new Blob(["prepared"]));
      session.updateRun({ faceReg: true, facePrompted: true, pouchReviewed: true });
    });
  if (guide) mocks.query = new URLSearchParams(`guideId=${GUIDE}`);
  show = true;
  await render();
}
async function click(label: string) {
  const button = Array.from(element.querySelectorAll("button")).find(
    (b) => b.textContent === label,
  );
  expect(button, label).toBeTruthy();
  await act(async () => button!.click());
}
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => saved.get(k) ?? null,
    setItem: (k: string, v: string) => saved.set(k, v),
  });
  vi.clearAllMocks();
  clearFacePhoto();
  vi.spyOn(api, "get").mockResolvedValue({
    user: { email: "test@example.com", nickname: "테스트" },
    csrfToken: "csrf",
  });
  mocks.query = new URLSearchParams("jobId=j1");
  mocks.live.job = job();
  mocks.live.pct = 0;
  mocks.live.error = null;
  mocks.register.mockReset().mockResolvedValue({ faceRegistrationId: "f1" });
  mocks.remove.mockResolvedValue(undefined);
  mocks.retry.mockReset();
  show = false;
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("분석 중 이용 준비", () => {
  it("같은 화면에서 가이드 준비로 바뀌어도 진행률은 100%다", async () => {
    await mount();
    await click("나중에");
    await click("파우치 확인 완료");
    const id = session.state.run.id;
    mocks.query = new URLSearchParams(`guideId=${GUIDE}`);
    await render();
    expect(element.querySelector('[data-testid="progress"]')?.textContent).toBe("0");
    await act(async () => session.continueAnalysis(id, "j1", GUIDE));
    expect(session.state.run.id).toBe(id);
    expect(element.querySelector('[data-testid="progress"]')?.textContent).toBe("100");
  });

  it.each(["분석 등록", "가이드 등록", "제품 확인 전 저장", "분석 재시도", "분석 상태"])(
    "%s의 401은 세션·사진·토큰을 정리한다",
    async (source) => {
      const unauthorized = new ApiError(401, "UNAUTHORIZED", "로그인 필요");
      await mount(
        source === "가이드 등록" || source === "제품 확인 전 저장",
        source === "제품 확인 전 저장",
      );
      const id = session.state.run.id;
      if (source === "분석 재시도") {
        await click("촬영 완료");
        await click("파우치 확인 완료");
        mocks.live.job = job({ status: "FAILED", retryable: true });
        await render();
        mocks.retry.mockRejectedValueOnce(unauthorized);
        await click("다시 시도");
      } else if (source === "분석 상태") {
        saveFacePhoto(id, new Blob(["face"]));
        mocks.live.error = unauthorized;
        await render();
      } else {
        mocks.register.mockRejectedValueOnce(unauthorized);
        await click(source === "제품 확인 전 저장" ? "제품 확인하기" : "촬영 완료");
      }
      expect(session.state).toMatchObject({
        loggedIn: false,
        sessionExpired: true,
        run: { id: "" },
      });
      expect(facePhoto(id)).toBeNull();
      expect(mocks.router.replace).toHaveBeenCalledWith("/login?expired=basic");
      const fetch = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValue(new Response("{}", { headers: { "Content-Type": "application/json" } }));
      await api.post("/v1/test-session-expiry", { mock: null });
      expect(new Headers(fetch.mock.calls[0][1]?.headers).has("X-CSRF-TOKEN")).toBe(false);
    },
  );

  it("대기열 0%부터 등록을 띄우고 완료하면 분석 중 파우치를 보여준다", async () => {
    await mount();
    expect(element.querySelector('[data-testid="face"]')).not.toBeNull();
    await click("촬영 완료");
    expect(mocks.register).toHaveBeenCalledWith(
      facePhoto(session.state.run.id),
      expect.objectContaining({ videoId: "v", guideId: null }),
    );
    expect(session.state.run.faceRegistrationId).toBe("f1");
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
    expect(element.querySelector('[data-testid="pouch"]')).not.toBeNull();
    await click("파우치 확인 완료");
    mocks.live.job = job({ status: "RUNNING", progressStage: "SEGMENTING" });
    mocks.live.pct = 25;
    await render();
    show = false;
    await render();
    show = true;
    await render();
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
    expect(element.querySelector('[data-testid="pouch"]')).toBeNull();
  });

  it("파우치를 닫은 뒤 분석 중 별도 버튼으로 다시 열 수 있다", async () => {
    await mount();
    await click("나중에");
    await click("파우치 확인 완료");
    await click("내 파우치 확인 / 추가");
    expect(element.querySelector('[data-testid="pouch"]')).not.toBeNull();
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
  });

  it("분석 중 저장 실패는 같은 사진으로 재시도하고 성공해야 파우치로 간다", async () => {
    await mount();
    mocks.register.mockRejectedValueOnce(new Error("저장 실패"));
    await click("촬영 완료");
    const photo = facePhoto(session.state.run.id);
    expect(element.querySelector('[role="alert"]')?.textContent).toContain("저장 실패");
    expect(element.querySelector('[data-testid="face"]')).not.toBeNull();
    expect(element.querySelector('[data-testid="pouch"]')).toBeNull();
    expect(session.state.run.faceRegistrationId).toBeNull();
    await click("촬영 완료");
    expect(mocks.register).toHaveBeenLastCalledWith(
      photo,
      expect.objectContaining({ videoId: "v", guideId: null }),
    );
    expect(session.state.run.faceRegistrationId).toBe("f1");
    expect(element.querySelector('[data-testid="pouch"]')).not.toBeNull();
  });

  it("분석 중 등록 응답 전에 실행을 바꾸면 늦게 생긴 서버 등록을 정리한다", async () => {
    await mount();
    let finish!: (value: { faceRegistrationId: string }) => void;
    mocks.register.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await click("촬영 완료");
    await act(async () => session.startRun({ kind: "sample", jobId: "other" }));
    await act(async () => finish({ faceRegistrationId: "stale-analysis" }));
    expect(mocks.remove).toHaveBeenCalledWith("stale-analysis");
    expect(session.state.run.faceRegistrationId).toBeNull();
    expect(mocks.router.push).not.toHaveBeenCalled();
  });

  it("이전 실행의 늦은 401은 새 실행을 만료시키지 않는다", async () => {
    await mount();
    let reject!: (reason: unknown) => void;
    mocks.register.mockImplementationOnce(
      () =>
        new Promise((_resolve, fail) => {
          reject = fail;
        }),
    );
    await click("촬영 완료");
    await act(async () => session.startRun({ kind: "sample", jobId: "other" }));
    const nextId = session.state.run.id;
    await act(async () => reject(new ApiError(401, "UNAUTHORIZED", "로그인 필요")));
    expect(session.state.loggedIn).toBe(true);
    expect(session.state.run.id).toBe(nextId);
    expect(mocks.router.replace).not.toHaveBeenCalled();
  });

  it("서버 등록이 끝난 사진은 제품 확인 진입 때 다시 업로드하지 않는다", async () => {
    await mount(true, true);
    await act(async () => session.updateRun({ faceRegistrationId: "already-saved" }));
    await click("제품 확인하기");
    expect(mocks.register).not.toHaveBeenCalled();
    expect(mocks.router.push).toHaveBeenCalledWith(`/check?guideId=${GUIDE}`);
  });

  it("등록을 미뤄도 파우치를 보여주고 자동 등록 안내를 반복하지 않는다", async () => {
    await mount();
    await click("나중에");
    expect(mocks.stop).toHaveBeenCalledOnce();
    expect(element.querySelector('[data-testid="pouch"]')).not.toBeNull();
    await click("파우치 확인 완료");
    show = false;
    await render();
    show = true;
    await render();
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
  });

  it("촬영 중 분석이 완료돼도 준비 화면을 유지하고 완료 후 파우치를 보여준다", async () => {
    await mount();
    mocks.live.job = job({ status: "COMPLETED", reviewStatus: "APPROVED", guideId: GUIDE });
    mocks.live.pct = 100;
    await render();
    expect(mocks.router.push).not.toHaveBeenCalled();
    expect(element.querySelector('[data-testid="face"]')).not.toBeNull();
    await click("촬영 완료");
    expect(element.querySelector('[data-testid="pouch"]')).not.toBeNull();
    await click("파우치 확인 완료");
    await click("가이드로 따라 하기");
    expect(mocks.router.push).toHaveBeenCalledWith(`/loading?guideId=${GUIDE}&jobId=j1`);
  });

  it.each([
    { status: "FAILED" as const },
    { status: "COMPLETED" as const, reviewStatus: "PENDING" as const },
    { status: "COMPLETED" as const, reviewStatus: "REJECTED" as const },
  ])("이미 종료된 작업에는 등록을 자동 표시하지 않는다: %j", async (over) => {
    mocks.live.job = job(over);
    mocks.live.pct = 100;
    await mount();
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
  });

  it("저장 실패 시 촬영한 사진으로 재시도하고 중복 요청을 막는다", async () => {
    await mount(true, true);
    const photo = facePhoto(session.state.run.id);
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
    mocks.register.mockRejectedValueOnce(new Error("저장 실패"));
    await click("제품 확인하기");
    expect(element.querySelector('[role="alert"]')?.textContent).toContain(
      "얼굴 등록을 저장하지 못했어요",
    );
    expect(facePhoto(session.state.run.id)).toBe(photo);
    let finish!: (value: { faceRegistrationId: string }) => void;
    mocks.register.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const button = Array.from(element.querySelectorAll("button")).find(
      (b) => b.textContent === "얼굴 등록 저장 다시 시도",
    )!;
    await act(async () => {
      button.click();
      button.click();
    });
    expect(mocks.register).toHaveBeenCalledTimes(2);
    await act(async () => finish({ faceRegistrationId: "f1" }));
    expect(mocks.register).toHaveBeenLastCalledWith(
      photo,
      expect.objectContaining({ videoId: "v", guideId: GUIDE }),
    );
    expect(session.state.run.faceRegistrationId).toBe("f1");
    expect(mocks.router.push).toHaveBeenCalledWith(`/check?guideId=${GUIDE}`);
  });

  it("이전 실행의 업로드가 늦게 끝나면 등록을 정리하고 이동하지 않는다", async () => {
    await mount(true, true);
    let finish!: (value: { faceRegistrationId: string }) => void;
    mocks.register.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await click("제품 확인하기");
    await act(async () => session.startRun({ kind: "sample", jobId: "other" }));
    await act(async () => finish({ faceRegistrationId: "stale" }));
    expect(mocks.remove).toHaveBeenCalledWith("stale");
    expect(mocks.router.push).not.toHaveBeenCalled();
    expect(session.state.run.faceRegistrationId).toBeNull();
  });

  it("분석 재시도로 다른 작업에 합류해도 촬영과 파우치 확인을 반복하지 않는다", async () => {
    await mount();
    await click("촬영 완료");
    await click("파우치 확인 완료");
    const id = session.state.run.id;
    const photo = facePhoto(id);
    mocks.live.job = job({ status: "FAILED", retryable: true });
    await render();
    mocks.retry.mockResolvedValue(job({ jobId: "j2" }));
    await click("다시 시도");
    expect(mocks.router.replace).toHaveBeenCalledWith("/loading?jobId=j2");
    mocks.query = new URLSearchParams("jobId=j2");
    mocks.live.job = job({ jobId: "j2" });
    await render();
    expect(session.state.run).toMatchObject({
      id,
      jobId: "j2",
      faceReg: true,
      pouchReviewed: true,
    });
    expect(facePhoto(id)).toBe(photo);
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
    expect(element.querySelector('[data-testid="pouch"]')).toBeNull();
  });

  it("완료된 가이드에서 수동으로 등록해도 파우치를 닫은 뒤 얼굴 등록이 다시 뜨지 않는다", async () => {
    await mount(true);
    await click("나중에");
    await click("파우치 확인 완료");
    await click("얼굴 등록하고 제품 확인");
    await click("촬영 완료");
    expect(mocks.register).toHaveBeenCalledOnce();
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
    expect(element.querySelector('[data-testid="pouch"]')).toBeNull();
    await render();
    expect(element.querySelector('[data-testid="face"]')).toBeNull();
  });
});
