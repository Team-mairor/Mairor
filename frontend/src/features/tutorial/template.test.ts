import { describe, expect, it } from "vitest";

import { templateFor, templateOf, withStepTemplate } from "./template";

describe("기본 가이드 고르기", () => {
  it("쉐딩 단계 이름에 코가 있으면 코 쉐딩 기본 가이드를 쓴다", () => {
    expect(templateFor("contour", "코 쉐딩")).toBe("contourNose");
    expect(templateFor("contour", "콧대 쉐딩")).toBe("contourNose");
    expect(templateFor("contour", "쉐딩")).toBe("contour");
    expect(templateFor("highlight", "코끝 하이라이트")).toBe("highlight");
  });

  it("영역이 없는 단계와 기본 가이드를 쓰는 하위 단계 모두 바꾼다", () => {
    expect(templateOf({ stepId: "s15", makeup: "contour", short: "코 쉐딩" }).templateId).toBe(
      "contourNose",
    );
    const sub = templateOf({ stepId: "s15", makeup: "contour", short: "쉐딩" });
    expect(withStepTemplate([sub], "코 쉐딩")[0].templateId).toBe("contourNose");
  });
});
