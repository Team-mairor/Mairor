import { describe, expect, it } from "vitest";

import type { AnalysisJobReceipt, PopularVideoItem, VideoSelection } from "@/lib/api";

import { targetOfPopular, targetOfReceipt, targetOfSelection } from "./start-target";

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";
const JOB_ID = "c0000000-0000-4000-8000-000000000001";

const selection = (patch: Partial<VideoSelection>): VideoSelection => ({
  videoId: "b0000000-0000-4000-8000-000000000001",
  youtubeVideoId: "VxAXD6PP76I",
  title: "데일리 메이크업",
  channelTitle: "채널",
  durationSeconds: 760,
  thumbnailUrl: null,
  viewCount: null,
  publishedAt: null,
  guideId: null,
  guideAvailable: false,
  chapters: [],
  analysisJobId: null,
  reviewStatus: null,
  ...patch,
});

const receipt = (patch: Partial<AnalysisJobReceipt>): AnalysisJobReceipt => ({
  jobId: JOB_ID,
  videoId: "b0000000-0000-4000-8000-000000000001",
  receiptType: "NEW_JOB",
  status: "PENDING",
  progressStage: "QUEUED",
  guideId: null,
  reviewStatus: "NOT_READY",
  pollAfterSeconds: 5,
  ...patch,
});

describe("targetOfSelection", () => {
  it("승인 가이드가 있으면 진행 중 분석보다 먼저 가이드로 시작한다", () => {
    expect(
      targetOfSelection(
        selection({ guideAvailable: true, guideId: GUIDE_ID, analysisJobId: JOB_ID }),
      ),
    ).toEqual({ kind: "guide", guideId: GUIDE_ID });
  });

  it("검수 전 가이드(guideAvailable=false)는 건너뛰고 내 진행 중 분석으로 간다", () => {
    expect(
      targetOfSelection(
        selection({ guideAvailable: false, guideId: GUIDE_ID, analysisJobId: JOB_ID }),
      ),
    ).toEqual({ kind: "job", jobId: JOB_ID });
  });

  it("둘 다 없으면 null이라 분석을 요청한다", () => {
    expect(targetOfSelection(selection({}))).toBeNull();
  });
});

describe("targetOfReceipt", () => {
  it("REUSED_GUIDE는 가이드로 시작한다", () => {
    expect(
      targetOfReceipt(receipt({ receiptType: "REUSED_GUIDE", jobId: null, guideId: GUIDE_ID })),
    ).toEqual({ kind: "guide", guideId: GUIDE_ID });
  });

  it.each(["NEW_JOB", "JOINED_JOB"] as const)("%s는 받은 작업의 로딩으로 간다", (type) => {
    expect(targetOfReceipt(receipt({ receiptType: type }))).toEqual({ kind: "job", jobId: JOB_ID });
  });

  it("받은 ID가 비면 null이다", () => {
    expect(targetOfReceipt(receipt({ receiptType: "REUSED_GUIDE", jobId: null }))).toBeNull();
    expect(targetOfReceipt(receipt({ jobId: null }))).toBeNull();
  });
});

describe("targetOfPopular", () => {
  const popular = (patch: Partial<PopularVideoItem>): PopularVideoItem => ({
    ...selection({}),
    rank: 1,
    ...patch,
  });

  it("승인 가이드가 있으면 가이드로 시작한다", () => {
    expect(targetOfPopular(popular({ guideAvailable: true, guideId: GUIDE_ID }))).toEqual({
      kind: "guide",
      guideId: GUIDE_ID,
    });
  });

  it("가이드가 없으면 null이라 videoId로 분석을 요청한다", () => {
    expect(targetOfPopular(popular({}))).toBeNull();
    expect(targetOfPopular(popular({ guideAvailable: true, guideId: null }))).toBeNull();
  });
});
