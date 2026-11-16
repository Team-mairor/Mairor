import { describe, expect, it } from "vitest";

import { templateFor, templateOf } from "./template";

describe("기본 가이드 고르기", () => {
  it("쉐딩 단계 이름에 코가 있으면 코 쉐딩 기본 가이드를 쓴다", () => {
    expect(templateFor("contour", "코 쉐딩")).toBe("contourNose");
    expect(templateFor("contour", "콧대 쉐딩")).toBe("contourNose");
    expect(templateFor("contour", "노즈 쉐딩")).toBe("contourNose");
    expect(templateFor("contour", "쉐딩")).toBe("contour");
    expect(templateFor("highlight", "코끝 하이라이트")).toBe("highlight");
  });

  it("코렉터·코랄은 코로 보지 않는다", () => {
    expect(templateFor("contour", "코렉터로 윤곽 정리")).toBe("contour");
    expect(templateFor("contour", "코랄 쉐딩")).toBe("contour");
  });

  it("영역이 없는 단계만 이름으로 기본 가이드를 고른다", () => {
    expect(templateOf({ stepId: "s15", makeup: "contour", short: "코 쉐딩" }).templateId).toBe(
      "contourNose",
    );
    expect(templateOf({ stepId: "s15", makeup: "contour", short: "쉐딩" }).templateId).toBe(
      "contour",
    );
  });

  it("코 블러셔 키와 영역 없는 단계의 볼 블러셔 키를 구분한다", () => {
    expect(templateFor("blushNose", "코 블러셔")).toBe("blushNose");
    expect(templateFor("blush", "코 블러셔")).toBe("blush");
    const sub = templateOf({ stepId: "s22b", makeup: "blush", short: "코 블러셔" });
    expect(sub.templateId).toBe("blush");
  });
});
