import { describe, expect, it } from "vitest";

import type { PhotoMeta, ReportRecordDto, ReportStepDto, ReportSummaryDto } from "@/lib/api";

import { fromRecord, fromSummary } from "./report-api";
import { guideReportRows } from "./report-rows";

const photo = (id: string): PhotoMeta => ({
  photoId: id,
  kind: "STEP",
  contentType: "image/jpeg",
  byteSize: 1,
  width: 1,
  height: 1,
  url: `/api/v1/users/me/photos/${id}`,
  createdAt: "2026-11-11T00:00:00Z",
});

const summary: ReportSummaryDto = {
  recordId: "r1",
  guideId: "g1",
  videoId: "v1",
  youtubeVideoId: "yt1",
  videoTitle: "데일리 메이크업",
  channelTitle: "채널",
  thumbnailUrl: null,
  completedAt: "2026-11-11T09:00:00Z",
  completedPhoto: photo("p9"),
  stepCount: 3,
  substituteCount: 1,
};

const step = (patch: Partial<ReportStepDto>): ReportStepDto => ({
  stepId: "s1",
  part: "blush",
  partLabel: null,
  summary: null,
  actions: [],
  referenceProduct: null,
  matchingResult: "NONE",
  selectedProduct: null,
  skipped: true,
  photo: null,
  ...patch,
});

const record: ReportRecordDto = {
  recordId: "r1",
  executionId: "e1",
  videoId: "v1",
  videoTitle: "데일리 메이크업",
  channelTitle: "채널",
  guideId: "g1",
  guideVersion: 2,
  completedAt: "2026-11-11T09:00:00Z",
  completedPhoto: null,
  stepCount: 3,
  substituteCount: 1,
  steps: [
    step({
      stepId: "s1",
      partLabel: "크림 블러셔",
      summary: "볼 중앙에 두드린다",
      referenceProduct: { name: "젤리 치크", shadeName: "02" },
      matchingResult: "SUBSTITUTE",
      selectedProduct: { brand: "클리오", name: "블러셔", shadeName: null },
      skipped: false,
      photo: photo("p1"),
    }),
    step({ stepId: "s2", actions: [{ text: "첫 동작" }] }),
    step({ stepId: "s3", part: "unknown-part", referenceProduct: { name: null, shadeName: null } }),
  ],
};

describe("fromSummary", () => {
  it("목록 한 줄을 리포트 카드로 바꾸고 완성 사진 주소를 남긴다", () => {
    expect(fromSummary(summary)).toEqual({
      id: "r1",
      guideId: "g1",
      title: "데일리 메이크업",
      date: `${new Date(summary.completedAt).getMonth() + 1}월 ${new Date(summary.completedAt).getDate()}일`,
      steps: 3,
      subs: 1,
      finalPhoto: true,
      photoUrl: "/api/v1/users/me/photos/p9",
      videoId: "v1",
    });
  });

  it("완성 사진이 없으면 미촬영으로 본다", () => {
    expect(fromSummary({ ...summary, completedPhoto: null })).toMatchObject({
      finalPhoto: false,
      photoUrl: null,
    });
  });
});

describe("fromRecord", () => {
  it("스냅샷 단계를 리포트 단계로 바꾼다", () => {
    const rep = fromRecord(record);
    expect(rep).toMatchObject({ id: "r1", guideVersion: 2, finalPhoto: false, photoUrl: null });
    expect(rep.guide?.steps).toEqual([
      {
        stepId: "s1",
        title: "크림 블러셔",
        summary: "볼 중앙에 두드린다",
        ref: { name: "젤리 치크", shade: "02" },
        pick: "picked",
        used: { brand: "클리오", name: "블러셔", shade: null },
        photo: true,
        photoUrl: "/api/v1/users/me/photos/p1",
      },
      {
        stepId: "s2",
        title: "블러셔",
        summary: "첫 동작",
        ref: null,
        pick: "skipped",
        used: null,
        photo: false,
        photoUrl: null,
      },
      expect.objectContaining({ stepId: "s3", title: "기타", summary: null, ref: null }),
    ]);
  });

  it("화면 줄에 단계 사진 주소가 그대로 간다", () => {
    const rows = guideReportRows(fromRecord(record).guide!);
    expect(rows.map((r) => [r.photo, r.photoUrl])).toEqual([
      ["slot", "/api/v1/users/me/photos/p1"],
      ["none", null],
      ["none", null],
    ]);
    expect(rows[1].usedKind).toBe("생략");
  });
});
