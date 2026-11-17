import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api";
import type { AnalysisJobStatus } from "@/lib/api";

import { describeLoading, jobFail, loadingCta } from "./loading-status";

const job = (over: Partial<AnalysisJobStatus> = {}): AnalysisJobStatus => ({
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

const base = {
  pct: 40,
  job: job(),
  activeJobId: "j1",
  replay: false,
  fail: null,
  review: null,
  approvedGuide: null,
  retryRefused: false,
  hasPicked: true,
  guideMode: false,
  guideReady: false,
} as const;

describe("jobFail", () => {
  it("로그인 만료(401)는 작업 실패로 보지 않는다", () => {
    const e = new ApiError(401, "UNAUTHORIZED", "만료", []);
    expect(jobFail(e, null)).toBeNull();
  });
  it("그 밖의 조회 오류는 열 수 없는 작업, FAILED는 멈춘 작업이다", () => {
    expect(jobFail(new ApiError(404, "NOT_FOUND", "없음", []), null)).toBe("missing");
    expect(jobFail(null, job({ status: "FAILED" }))).toBe("stopped");
    expect(jobFail(null, job())).toBeNull();
  });
});

describe("describeLoading", () => {
  it("진행 중에는 안내 카드가 없고 가이드도 아직 준비되지 않았다", () => {
    const s = describeLoading(base);
    expect(s.done).toBe(false);
    expect(s.notice).toBeNull();
    expect(s.guideOk).toBe(false);
    expect(s.guideState).toBe("분석 중 40%");
    expect(s.eta).toBe("처리 중");
  });
  it("멈춘 작업은 멈춤으로 안내하고 다시 시도 여부를 서버 판단으로 정한다", () => {
    const failed = job({ status: "FAILED", retryable: true });
    const s = describeLoading({ ...base, job: failed, fail: "stopped" });
    expect(s.guideState).toBe("멈춤");
    expect(s.scanStatus).toMatch(/^STOPPED/);
    expect(s.notice?.retry).toBe(true);
    const refused = describeLoading({ ...base, job: failed, fail: "stopped", retryRefused: true });
    expect(refused.notice?.retry).toBe(false);
  });
  it("조회할 수 없는 작업은 NOT FOUND로 안내한다", () => {
    const s = describeLoading({ ...base, job: null, fail: "missing" });
    expect(s.notice?.tag).toBe("NOT FOUND");
    expect(s.phaseLabel).toBe("작업을 찾지 못했어요");
  });
  it("완료 후 검수 대기·반려·승인에 맞는 안내를 고른다", () => {
    const done = { ...base, pct: 100 };
    expect(describeLoading({ ...done, review: "pending" }).notice?.tag).toBe("IN REVIEW");
    expect(describeLoading({ ...done, review: "pending" }).guideState).toBe("검수 대기");
    expect(describeLoading({ ...done, review: "rejected" }).notice?.tag).toBe("REJECTED");
    const ok = describeLoading({ ...done, approvedGuide: "g1" });
    expect(ok.notice?.tag).toBe("READY");
    expect(ok.guideOk).toBe(true);
    expect(ok.guideState).toBe("준비 완료");
  });
  it("검수 대기 안내는 고른 영상을 알 때만 홈 안내를 덧붙인다", () => {
    const s = (hasPicked: boolean) =>
      describeLoading({ ...base, pct: 100, review: "pending", hasPicked }).notice?.sub;
    expect(s(true)).toContain("홈에서");
    expect(s(false)).not.toContain("홈에서");
  });
  it("분석 없이 시작하는 다시 하기는 바로 준비된 것으로 본다", () => {
    const s = describeLoading({ ...base, pct: 100, job: null, activeJobId: null, replay: true });
    expect(s.guideOk).toBe(true);
    expect(s.phaseLabel).toBe("분석이 끝났어요");
  });
  it("영상에서 찾은 제품을 행으로 만들고 보유 수를 센다", () => {
    const found = job({
      foundProducts: [
        {
          stepId: "s1",
          part: "lip",
          ownership: "OWNED",
          referenceProduct: { name: "틴트" },
        },
        {
          stepId: "s2",
          part: "blush",
          ownership: "MISSING",
          referenceProduct: { name: "블러셔" },
        },
      ] as AnalysisJobStatus["foundProducts"],
    });
    const s = describeLoading({ ...base, job: found });
    expect(s.rows.map((r) => r.cat)).toEqual(["립", "블러셔"]);
    expect(s.foundCount).toBe(2);
    expect(s.haveCount).toBe(1);
  });
});

describe("loadingCta", () => {
  const ready = {
    approvedGuide: null,
    review: null,
    guideOk: true,
    faceCaptured: true,
    faceOk: true,
    guideMode: true,
    savingFace: false,
    faceSaveError: null,
  } as const;

  it("승인된 가이드가 있으면 가이드로 넘어간다", () => {
    expect(loadingCta({ ...ready, approvedGuide: "g1" }).action).toBe("guide");
  });
  it("검수 대기는 홈으로, 반려는 다른 영상 고르기로 보낸다", () => {
    expect(loadingCta({ ...ready, review: "pending" })).toEqual({
      label: "홈으로",
      action: "home",
    });
    expect(loadingCta({ ...ready, review: "rejected" }).action).toBe("select");
  });
  it("가이드가 아직 준비되지 않았으면 누를 수 없다", () => {
    expect(loadingCta({ ...ready, guideOk: false }).action).toBeNull();
  });
  it("얼굴 촬영 전에는 등록을 열고, 서버 저장이 안 됐으면 저장을 다시 시도한다", () => {
    expect(loadingCta({ ...ready, faceCaptured: false }).action).toBe("face");
    const retry = loadingCta({ ...ready, faceOk: false, faceSaveError: "실패" });
    expect(retry).toEqual({ label: "얼굴 등록 저장 다시 시도", action: "save-face" });
    const saving = loadingCta({ ...ready, faceOk: false, savingFace: true });
    expect(saving.action).toBeNull();
  });
  it("모두 준비되면 미리보기로 간다", () => {
    expect(loadingCta(ready)).toEqual({ label: "제품 확인하기", action: "check" });
  });
});
