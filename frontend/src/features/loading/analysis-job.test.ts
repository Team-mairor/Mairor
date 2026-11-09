import { describe, expect, it } from "vitest";

import type { AnalysisJobStatus } from "@/lib/api";

import { isJobSettled, jobPercent, jobReview, stageText } from "./analysis-job";

const job = (over: Partial<AnalysisJobStatus>): AnalysisJobStatus => ({
  jobId: "j",
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
  createdAt: "2026-11-06T00:00:00Z",
  completedAt: null,
  ...over,
});

describe("jobPercent", () => {
  it("단계 시작 %에서 출발하고 가이드 구성은 단계 안 숫자로 채운다", () => {
    expect(jobPercent(job({ progressStage: "QUEUED" }))).toBe(0);
    expect(jobPercent(job({ progressStage: "SEGMENTING" }))).toBe(12);
    expect(jobPercent(job({ progressStage: "BUILDING_GUIDE" }))).toBe(80);
    // 80~100을 넷으로 나눈 두 번째 칸(LANDMARKS)의 절반 → 80 + 20 * 1.5 / 4
    const half = { item: "LANDMARKS", done: 1000, total: 2000 } as const;
    expect(jobPercent(job({ progressStage: "BUILDING_GUIDE", stageProgress: half }))).toBe(87);
  });

  it("끝나기 전에는 99를 넘지 않고 완료면 100", () => {
    const full = { item: "EXPLANATION", done: 19, total: 19 } as const;
    expect(jobPercent(job({ progressStage: "BUILDING_GUIDE", stageProgress: full }))).toBe(99);
    expect(jobPercent(job({ status: "COMPLETED", progressStage: "DONE" }))).toBe(100);
  });

  it("total이 0이면 단계 시작 %", () => {
    const zero = { item: "FRAMES", done: 0, total: 0 } as const;
    expect(jobPercent(job({ progressStage: "BUILDING_GUIDE", stageProgress: zero }))).toBe(80);
  });

  it("모르는 단계·item이 와도 예외 없이 계산한다", () => {
    const stage = "NEW_STAGE" as AnalysisJobStatus["progressStage"];
    expect(jobPercent(job({ progressStage: stage }))).toBe(0);
    const odd = { item: "NEW_ITEM" as "FRAMES", done: 1, total: 2 };
    expect(jobPercent(job({ progressStage: "BUILDING_GUIDE", stageProgress: odd }))).toBe(80);
    expect(stageText(odd)).toBeNull();
  });
});

describe("stageText", () => {
  it("item별 문구와 천 단위 쉼표", () => {
    expect(stageText({ item: "LANDMARKS", done: 840, total: 2000 })).toBe(
      "얼굴 분석 840 / 2,000장",
    );
    expect(stageText({ item: "AREA", done: 8, total: 19 })).toBe(
      "가이드 영역 만드는 중 8 / 19단계",
    );
    expect(stageText(null)).toBeNull();
  });
});

describe("isJobSettled · jobReview", () => {
  it("실패·승인·반려에서 닫고 검수 대기는 계속 받는다", () => {
    expect(isJobSettled(job({}))).toBe(false);
    expect(isJobSettled(job({ status: "FAILED" }))).toBe(true);
    expect(isJobSettled(job({ status: "COMPLETED", reviewStatus: "PENDING" }))).toBe(false);
    expect(isJobSettled(job({ status: "COMPLETED", reviewStatus: "APPROVED" }))).toBe(true);
    expect(isJobSettled(job({ status: "COMPLETED", reviewStatus: "REJECTED" }))).toBe(true);
  });

  it("검수 표시", () => {
    expect(jobReview(job({}))).toBeNull();
    expect(jobReview(job({ status: "COMPLETED", reviewStatus: "PENDING" }))).toBe("pending");
    expect(jobReview(job({ status: "COMPLETED", reviewStatus: "APPROVED" }))).toBeNull();
    expect(jobReview(job({ status: "COMPLETED", reviewStatus: "REJECTED" }))).toBe("rejected");
  });
});
