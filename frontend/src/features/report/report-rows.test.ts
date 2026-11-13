import { describe, expect, it } from "vitest";

import type { GuideReportStep } from "@/features/session";
import { deleteStepPhotos, saveStepPhoto } from "@/features/session";

import { captureTiles, guideReportRows, type ReportRow } from "./report-rows";

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

  it("단계 사진은 순번이 아니라 stepId로 그 실행의 사진을 붙인다", () => {
    const photo = { url: "data:image/jpeg;base64,s9", box: null };
    saveStepPhoto("run1", "s9", photo);
    const rows = guideReportRows(
      report([step("s1", { photo: true }), step("s9", { photo: true }), step("s3")]),
      "run1",
    );
    expect(rows.map((r) => [r.photo, "shot" in r ? r.shot : undefined])).toEqual([
      ["slot", undefined],
      ["shot", photo],
      ["none", undefined],
    ]);
    deleteStepPhotos("run1");
  });
});

const row = (
  no: number,
  category: ReportRow["category"],
  photo: "none" | "slot" | "sample",
): ReportRow => ({
  no,
  title: `단계 ${no}`,
  category,
  guide: "",
  ref: "",
  usedKind: "",
  used: "",
  photo,
});

describe("captureTiles", () => {
  it("연속한 같은 부위를 한 칸으로 묶고 묶음에서 사진을 남긴 마지막 단계를 쓴다", () => {
    const tiles = captureTiles([
      row(1, "BASE", "none"),
      row(2, "BASE", "slot"),
      row(3, "BASE", "none"),
      row(4, "LIP", "none"),
    ]);
    expect(tiles.map((t) => [t.no, t.label, t.row.no])).toEqual([
      [1, "피부", 2],
      [2, "입술", 4],
    ]);
  });

  it("찍은 사진이 여러 장인 묶음은 단계마다 찍던 이전 기록이라 사진마다 한 칸이다", () => {
    const tiles = captureTiles([
      row(1, "BASE", "slot"),
      row(2, "BASE", "none"),
      row(3, "BASE", "slot"),
      row(4, "LIP", "slot"),
    ]);
    expect(tiles.map((t) => [t.no, t.label, t.row.no])).toEqual([
      [1, "단계 1", 1],
      [2, "단계 3", 3],
      [3, "입술", 4],
    ]);
  });

  it("샘플 사진만 있는 묶음은 그대로 한 칸이다", () => {
    const tiles = captureTiles([row(1, "BASE", "sample"), row(2, "BASE", "sample")]);
    expect(tiles.map((t) => [t.label, t.row.no])).toEqual([["피부", 2]]);
  });

  it("부위를 모르는 이전 기록은 단계마다 한 칸이다", () => {
    const tiles = captureTiles([row(1, null, "slot"), row(2, null, "slot")]);
    expect(tiles.map((t) => [t.label, t.row.no])).toEqual([
      ["단계 1", 1],
      ["단계 2", 2],
    ]);
  });
});
