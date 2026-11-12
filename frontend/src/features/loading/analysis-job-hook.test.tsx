// @vitest-environment jsdom
import { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, type AnalysisJobStatus } from "@/lib/api";

import { jobPercent, retryAnalysisJob, useAnalysisJob } from "./analysis-job";

/** 연결을 열고 닫은 것만 기록하고, 테스트가 status 이벤트를 보낸다 */
class FakeEventSource {
  static all: FakeEventSource[] = [];
  static readonly CLOSED = 2;
  readyState = 1;
  onerror: (() => void) | null = null;
  private listeners: ((e: MessageEvent<string>) => void)[] = [];
  constructor(readonly url: string) {
    FakeEventSource.all.push(this);
  }
  addEventListener(_type: string, fn: (e: MessageEvent<string>) => void) {
    this.listeners.push(fn);
  }
  close() {
    this.readyState = FakeEventSource.CLOSED;
  }
  send(job: AnalysisJobStatus) {
    for (const fn of this.listeners) fn({ data: JSON.stringify(job) } as MessageEvent<string>);
  }
}

const job = (over: Partial<AnalysisJobStatus>): AnalysisJobStatus => ({
  jobId: "j1",
  videoId: "v",
  status: "RUNNING",
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
let latest: ReturnType<typeof useAnalysisJob>;

function Probe({ jobId }: { jobId: string }) {
  const value = useAnalysisJob(jobId);
  useLayoutEffect(() => {
    latest = value;
  });
  return null;
}

beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  FakeEventSource.all = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  root = createRoot(document.createElement("div"));
  await act(async () => root.render(<Probe jobId="j1" />));
});

afterEach(async () => {
  await act(async () => root.unmount());
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useAnalysisJob restart", () => {
  it("재시도한 상태로 바꾸고 진행률을 되돌린 뒤 상태를 다시 받는다", async () => {
    const failed = job({ status: "FAILED", progressStage: "BUILDING_GUIDE", retryable: true });
    await act(async () => FakeEventSource.all[0].send(failed));
    expect(FakeEventSource.all[0].readyState).toBe(FakeEventSource.CLOSED);
    const before = latest.pct;
    expect(before).toBe(jobPercent(failed));

    const queued = job({ status: "PENDING", progressStage: "QUEUED" });
    await act(async () => latest.restart(queued));

    expect(latest.job).toEqual(queued);
    expect(latest.pct).toBe(jobPercent(queued));
    expect(latest.pct).toBeLessThan(before);
    expect(FakeEventSource.all).toHaveLength(2);
    expect(FakeEventSource.all[1].url).toContain("/analysis-jobs/j1/events");

    const loading = job({ status: "RUNNING", progressStage: "LOADING_VIDEO" });
    await act(async () => FakeEventSource.all[1].send(loading));
    expect(latest.job?.progressStage).toBe("LOADING_VIDEO");
    expect(latest.pct).toBe(jobPercent(loading));
  });
});

describe("retryAnalysisJob", () => {
  it("작업의 재시도 주소로 보낸다", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue(job({ status: "PENDING" }));

    await retryAnalysisJob("a b");

    expect(post).toHaveBeenCalledWith("/v1/users/me/analysis-jobs/a%20b/retry");
  });
});
