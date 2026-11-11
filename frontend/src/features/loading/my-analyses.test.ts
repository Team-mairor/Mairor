import { describe, expect, it } from "vitest";

import type { AnalysisJobSummary } from "@/lib/api";

import { toPendingGuide } from "./my-analyses";

const GUIDE_ID = "a0000000-0000-4000-8000-000000000001";

const summary = (patch: Partial<AnalysisJobSummary>): AnalysisJobSummary => ({
  jobId: "c0000000-0000-4000-8000-000000000001",
  videoId: "b0000000-0000-4000-8000-000000000001",
  youtubeVideoId: "VxAXD6PP76I",
  title: "데일리 메이크업",
  thumbnailUrl: null,
  status: "COMPLETED",
  reviewStatus: "PENDING",
  guideId: null,
  requestedAt: "2026-11-11T08:00:00Z",
  reviewedAt: null,
  ...patch,
});

describe("toPendingGuide", () => {
  it("검수 중이면 검수 대기 카드", () => {
    expect(toPendingGuide(summary({}))).toEqual({
      title: "데일리 메이크업",
      ytid: "VxAXD6PP76I",
      status: "pending",
    });
  });

  it("승인되면 guideId로 바로 따라 할 수 있는 카드", () => {
    expect(toPendingGuide(summary({ reviewStatus: "APPROVED", guideId: GUIDE_ID }))).toEqual({
      title: "데일리 메이크업",
      ytid: "VxAXD6PP76I",
      status: "approved",
      guideId: GUIDE_ID,
    });
  });

  it("승인인데 guideId가 없거나 반려면 카드가 없다", () => {
    expect(toPendingGuide(summary({ reviewStatus: "APPROVED" }))).toBeNull();
    expect(toPendingGuide(summary({ reviewStatus: "REJECTED" }))).toBeNull();
  });
});
