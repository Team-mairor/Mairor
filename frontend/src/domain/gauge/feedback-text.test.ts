import { describe, expect, it } from "vitest";

import {
  bundleMessages,
  renderMessage,
  stepMessages,
  type FeedbackEvaluation,
  type FeedbackMessage,
} from "./feedback-text";
import { THRESHOLDS } from "./step-evaluation";
import spec from "../../../../shared/gauge/feedback_text.v1.json" with { type: "json" };

type Case = (typeof spec.cases)[number];

const messagesOf = (c: Case) => stepMessages(c.evaluation as FeedbackEvaluation, c.makeup);

const withoutText = (m: (typeof spec.cases)[number]["expected"][number]) => ({
  key: m.key,
  subStepId: m.subStepId,
  makeup: m.makeup,
  where: m.where,
  side: m.side,
  reason: m.reason,
});

const plain = (m: FeedbackMessage) => ({
  key: m.key,
  subStepId: m.subStepId,
  makeup: m.makeup,
  where: m.where,
  side: m.side,
  reason: m.reason,
});

describe("안내 문장은 AI 기대값과 같다", () => {
  for (const c of spec.cases) {
    it(c.name, () => {
      const out = messagesOf(c);
      expect(out.map(plain)).toEqual(c.expected.map(withoutText));
      expect(out.map(renderMessage)).toEqual(c.expected.map((m) => m.text));
    });
  }

  for (const bundle of spec.bundles) {
    it(`묶음 ${bundle.name}`, () => {
      const steps = bundle.steps.map((name) => {
        const found = spec.cases.find((c) => c.name === name);
        if (!found) throw new Error(`사례 ${name}이 없다`);
        return messagesOf(found);
      });
      const out = bundleMessages(steps);
      expect(out.map(plain)).toEqual(bundle.expected.map(withoutText));
      expect(out.map(renderMessage)).toEqual(bundle.expected.map((m) => m.text));
    });
  }

  it("평가 계산이 쓰는 기준값과 문장 규칙의 기준값이 같다", () => {
    expect(spec.thresholds).toMatchObject(THRESHOLDS);
  });

  it("묶음 순서와 좌우 방향 규칙은 규격의 값(step · regions)을 따른다", () => {
    expect(spec.bundleOrder).toBe("step");
    expect(spec.sideWhere).toBe("regions");
  });

  it("점수 · 합격 · 숫자 표현을 문장에 쓰지 않는다", () => {
    const all = spec.cases.flatMap((c) => messagesOf(c).map(renderMessage));
    expect(all.length).toBeGreaterThan(0);
    for (const text of all) expect(text).not.toMatch(/\d|점|합격|실패|잘했/);
  });
});
