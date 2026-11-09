import { afterEach, describe, expect, it, vi } from "vitest";

import { GuideContractError, toGuideArea, toGuideModel } from "./guide-model";

const ID = "11111111-1111-4111-8111-111111111111";

const step = (stepId: string, order: number, extra: Record<string, unknown> = {}) => ({
  stepId,
  order,
  type: "GUIDE",
  part: "blush",
  partLabel: "블러셔",
  summary: null,
  actions: [],
  doneWhen: null,
  tools: [],
  referenceProduct: null,
  targetColor: null,
  videoRange: { startSeconds: 0, endSeconds: 1 },
  previewable: true,
  matchCategory: "CHEEK",
  subSteps: [],
  ...extra,
});

const guide = (steps: unknown[], extra: Record<string, unknown> = {}) => ({
  guideId: ID,
  guideVersion: 1,
  videoId: "v1",
  youtubeVideoId: "yt",
  title: "영상",
  channelTitle: "채널",
  thumbnailUrl: null,
  meshVersion: "v1",
  referenceImageUrl: null,
  stepCount: steps.filter((s) => (s as { type: string }).type === "GUIDE").length,
  previewableStepCount: 0,
  steps,
  ...extra,
});

afterEach(() => vi.restoreAllMocks());

describe("toGuideModel", () => {
  it("EXCLUDED를 빼고 GUIDE 단계를 order 순으로 담는다", () => {
    const model = toGuideModel(
      guide([
        step("s3", 3),
        step("s1", 1, { type: "EXCLUDED", part: "other" }),
        step("s2", 2, { part: "lip" }),
      ]),
      ID,
    );
    expect(model.steps.map((s) => s.stepId)).toEqual(["s2", "s3"]);
  });

  it("같은 화장 종류의 단계를 합치지 않는다", () => {
    const model = toGuideModel(guide([step("s1", 1), step("s2", 2)]), ID);
    expect(model.steps).toHaveLength(2);
  });

  it("비어 있는 제품·동작·부위 이름을 정상으로 받는다", () => {
    const [s] = toGuideModel(guide([step("s1", 1, { partLabel: null })]), ID).steps;
    expect(s.label).toBe("블러셔");
    expect(s.product).toBeNull();
    expect(s.actions).toEqual([]);
  });

  it("제품 이름과 호수를 나누지 않고 그대로 쓴다", () => {
    const product = { name: "롬앤 베러 댄 팔레트", shadeName: "06 포멜로 로즈" };
    const [s] = toGuideModel(guide([step("s1", 1, { referenceProduct: product })]), ID).steps;
    expect(s.product).toEqual({ name: "롬앤 베러 댄 팔레트", shade: "06 포멜로 로즈" });
  });

  it("파우치 대분류는 아는 값만 보존한다", () => {
    const steps = toGuideModel(
      guide([
        step("s1", 1),
        step("s2", 2, { matchCategory: null }),
        step("s3", 3, { matchCategory: "cheek" }),
      ]),
      ID,
    ).steps;
    expect(steps.map((s) => s.matchCategory)).toEqual(["CHEEK", null, null]);
  });

  it("요청한 가이드가 아니면 쓰지 않는다", () => {
    expect(() => toGuideModel(guide([]), "other-id")).toThrow(GuideContractError);
  });

  it.each([
    ["a0000000-0000-4000-8000-000000000001", "A0000000-0000-4000-8000-000000000001"],
    ["A0000000-0000-4000-8000-000000000001", "a0000000-0000-4000-8000-000000000001"],
  ])("UUID 대소문자만 다르면 같은 가이드로 받는다 (%s → %s)", (responseId, requestId) => {
    const model = toGuideModel(guide([], { guideId: responseId }), requestId);
    expect(model.guideId).toBe(requestId);
  });

  it.each([null, undefined, 123, {}])(
    "응답 가이드 ID가 문자열이 아니면 쓰지 않는다 (%j)",
    (guideId) => {
      expect(() => toGuideModel(guide([], { guideId }), ID)).toThrow(GuideContractError);
    },
  );

  it("단계 ID나 순서가 겹치면 쓰지 않는다", () => {
    expect(() => toGuideModel(guide([step("s1", 1), step("s1", 2)]), ID)).toThrow(/s1/);
    expect(() => toGuideModel(guide([step("s1", 1), step("s2", 1)]), ID)).toThrow(/1/);
  });

  it("알 수 없는 단계 종류는 쓰지 않는다", () => {
    expect(() => toGuideModel(guide([step("s1", 1, { type: "OPTIONAL" })]), ID)).toThrow(
      GuideContractError,
    );
  });

  it("단계 수가 서버 값과 달라도 실제 단계로 쓰고 경고만 남긴다", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const model = toGuideModel(guide([step("s1", 1)], { stepCount: 5 }), ID);
    expect(model.steps).toHaveLength(1);
    expect(warn).toHaveBeenCalledOnce();
  });

  it.each(["constructor", "toString", "unknown"])("모르는 화장 종류는 기타로 본다 (%s)", (part) => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const [s] = toGuideModel(guide([step("s1", 1, { part, partLabel: null })]), ID).steps;
    expect(s.makeup).toBe("other");
    expect(s.label).toBe("기타");
  });

  it("모양이 틀린 하위 단계만 빼고 경고를 남긴다", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const sub = {
      subStepId: "s1-1",
      order: 1,
      status: "template",
      reasons: [],
      templateId: "blush",
      guideSets: [],
    };
    const subSteps = [sub, null, "s1-2", { ...sub, subStepId: "" }, { ...sub, status: "done" }];
    const [s] = toGuideModel(guide([step("s1", 1, { subSteps })]), ID).steps;
    expect(s.subSteps).toEqual([sub]);
    expect(warn).toHaveBeenCalledTimes(4);
  });

  it("GUIDE 단계가 없으면 빈 목록이다", () => {
    expect(toGuideModel(guide([]), ID).steps).toEqual([]);
  });
});

describe("toGuideArea", () => {
  it("영역이 없는 가이드(meshVersion null)는 null이다", () => {
    expect(toGuideArea(toGuideModel(guide([step("s1", 1)], { meshVersion: null }), ID))).toBeNull();
  });

  it("단계 ID·화장 종류·하위 단계를 그대로 옮긴다", () => {
    const sub = {
      subStepId: "s1-1",
      order: 1,
      status: "template",
      reasons: ["notAnalyzed"],
      templateId: "blush",
      guideSets: [],
    };
    const area = toGuideArea(toGuideModel(guide([step("s1", 1, { subSteps: [sub] })]), ID));
    expect(area?.steps).toEqual([{ stepId: "s1", order: 1, makeup: "blush", subSteps: [sub] }]);
  });
});
