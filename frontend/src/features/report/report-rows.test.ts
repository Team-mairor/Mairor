import { describe, expect, it } from "vitest";

import type { GuideReportStep } from "@/features/session";

import { guideReportRows } from "./report-rows";

const step = (stepId: string, extra: Partial<GuideReportStep> = {}): GuideReportStep => ({
  stepId,
  title: "블러셔",
  summary: "볼에 두드린다",
  ref: { name: "롬앤 베러 댄 치크", shade: "01" },
  pick: "undecided",
  used: null,
  photo: false,
  ...extra,
});

const report = (steps: GuideReportStep[]) => ({
  videoId: "v",
  youtubeVideoId: null,
  channelTitle: "채널",
  steps,
});

describe("guideReportRows", () => {
  it("스냅샷의 제목·설명·영상 제품을 그대로 쓴다", () => {
    const [row] = guideReportRows(report([step("s1")]));
    expect(row).toMatchObject({
      no: 1,
      title: "블러셔",
      guide: "볼에 두드린다",
      ref: "롬앤 베러 댄 치크 01",
    });
  });

  it("설명이 없으면 그렇게 알린다", () => {
    const [row] = guideReportRows(report([step("s1", { summary: null })]));
    expect(row.guide).toBe("영상에서 설명을 찾지 못했어요");
  });

  it("영상 제품 정보가 없으면 그렇게 알린다", () => {
    const [row] = guideReportRows(report([step("s1", { ref: null })]));
    expect(row.ref).toBe("영상에서 제품 정보를 찾지 못했어요");
  });

  it("선택·생략·미확정을 동일·대체 라벨 없이 나눠 보여 준다", () => {
    const rows = guideReportRows(
      report([
        step("s1", { pick: "picked", used: { brand: "클리오", name: "블러셔", shade: null } }),
        step("s2", { pick: "skipped" }),
        step("s3"),
      ]),
    );
    expect(rows.map((r) => [r.usedKind, r.used])).toEqual([
      ["내가 고른 제품", "클리오 블러셔"],
      ["생략", "이 단계는 제품을 쓰지 않았어요"],
      ["사용 제품", "기록 없음"],
    ]);
    expect(rows.some((r) => /동일|대체/.test(r.usedKind))).toBe(false);
  });

  it("남긴 사진은 사진 자리, 아니면 미촬영이다", () => {
    const rows = guideReportRows(report([step("s1", { photo: true }), step("s2")]));
    expect(rows.map((r) => r.photo)).toEqual(["slot", "none"]);
  });
});
