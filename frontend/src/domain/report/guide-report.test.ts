import { describe, expect, it } from "vitest";

import type { GuideModel, GuideStepModel } from "@/domain/guide";
import type { PouchItem } from "@/domain/pouch";

import { buildGuideReport, guideReportSummary, pickedCount } from "./guide-report";

const step = (stepId: string, extra: Partial<GuideStepModel> = {}): GuideStepModel => ({
  stepId,
  order: 1,
  makeup: "blush",
  label: "블러셔",
  summary: null,
  actions: [],
  doneWhen: null,
  product: { name: "롬앤 베러 댄 치크", shade: "01 쥬시 코랄" },
  matchCategory: "CHEEK",
  subSteps: [],
  ...extra,
});

const guide = (steps: GuideStepModel[]): GuideModel => ({
  guideId: "g1",
  guideVersion: 3,
  videoId: "v1",
  youtubeVideoId: "yt1",
  thumbnailUrl: null,
  title: "데일리 메이크업",
  channelTitle: "채널",
  meshVersion: null,
  steps,
});

const pouch: PouchItem[] = [
  { id: "p1", cat: "치크", type: "블러셔", brand: "클리오", name: "프리즘 블러셔", shade: "03" },
];

const run = (extra: Partial<{ photoOk: boolean; captures: string[] }> = {}) => ({
  choice: { s1: { kind: "pouch", id: "p1" }, s2: { kind: "none" } } as const,
  captures: ["s1", "s3"],
  photoOk: true,
  ...extra,
});

const steps = [step("s1"), step("s2"), step("s3", { product: null })];

describe("buildGuideReport", () => {
  it("단계마다 선택·생략·미확정을 나눠 남긴다", () => {
    const report = buildGuideReport(guide(steps), run(), pouch);
    expect(report.steps.map((s) => [s.stepId, s.pick, s.used])).toEqual([
      ["s1", "picked", { brand: "클리오", name: "프리즘 블러셔", shade: "03" }],
      ["s2", "skipped", null],
      ["s3", "undecided", null],
    ]);
  });

  it("고른 제품이 지워졌으면 미확정으로 남긴다", () => {
    const report = buildGuideReport(guide(steps), run(), []);
    expect(report.steps[0]).toMatchObject({ pick: "undecided", used: null });
  });

  it("파우치가 나중에 바뀌어도 남긴 값은 그대로다", () => {
    const items = pouch.map((p) => ({ ...p }));
    const report = buildGuideReport(guide(steps), run(), items);
    items[0].name = "바뀐 이름";
    expect(report.steps[0].used?.name).toBe("프리즘 블러셔");
  });

  it("영상 제품 이름과 호수를 그대로 남긴다", () => {
    const report = buildGuideReport(guide(steps), run(), pouch);
    expect(report.steps.map((s) => s.ref)).toEqual([
      { name: "롬앤 베러 댄 치크", shade: "01 쥬시 코랄" },
      { name: "롬앤 베러 댄 치크", shade: "01 쥬시 코랄" },
      null,
    ]);
  });

  it("설명은 요약, 없으면 첫 동작이다", () => {
    const report = buildGuideReport(
      guide([
        step("s1", { summary: "요약" }),
        step("s2", { actions: [{ text: "볼에 두드린다", tip: null }] }),
        step("s3"),
      ]),
      run(),
      pouch,
    );
    expect(report.steps.map((s) => s.summary)).toEqual(["요약", "볼에 두드린다", null]);
  });

  it("촬영 기록은 stepId로 판정하고 사진 동의가 없으면 모두 미촬영이다", () => {
    expect(buildGuideReport(guide(steps), run(), pouch).steps.map((s) => s.photo)).toEqual([
      true,
      false,
      true,
    ]);
    const noPhoto = buildGuideReport(guide(steps), run({ photoOk: false }), pouch);
    expect(noPhoto.steps.every((s) => !s.photo)).toBe(true);
  });
});

describe("guideReportSummary", () => {
  it("가이드 ID·판·단계 수와 마지막 단계 사진을 요약한다", () => {
    const summary = guideReportSummary("rp-1", new Date(2026, 10, 8), guide(steps), run(), pouch);
    expect(summary).toMatchObject({
      id: "rp-1",
      guideId: "g1",
      guideVersion: 3,
      title: "데일리 메이크업",
      date: "11월 8일",
      steps: 3,
      noPhoto: false,
      finalPhoto: true,
      videoId: "v1",
    });
    expect(summary.items).toBeUndefined();
    expect(summary.captures).toBeUndefined();
  });

  it("마지막 단계를 찍지 않았으면 완성 사진이 없다", () => {
    const summary = guideReportSummary(
      "rp-1",
      new Date(),
      guide(steps),
      run({ captures: ["s1"] }),
      pouch,
    );
    expect(summary.finalPhoto).toBe(false);
  });

  it("고른 제품 수를 센다", () => {
    expect(pickedCount(buildGuideReport(guide(steps), run(), pouch))).toBe(1);
  });
});
