// @vitest-environment jsdom
import { describe, expect, it } from "vitest";

import { parsePouch } from "./pouch-store";
import { parseReports } from "./report-store";

describe("저장값 읽기", () => {
  it("파우치는 예전 목업 항목을 빼고 읽는다", () => {
    expect(parsePouch([{ id: "p1" }, { id: "900" }, { id: "p12" }, { id: "abc" }])).toEqual([
      { id: "900" },
      { id: "abc" },
    ]);
  });

  it("리포트는 예전 목업 항목을 빼고 읽는다", () => {
    expect(parseReports([{ id: "rp1" }, { id: "rp4" }, { id: "rp5" }, { id: "d1" }])).toEqual([
      { id: "rp5" },
      { id: "d1" },
    ]);
  });

  it("목록이 아니면 읽지 않는다", () => {
    expect(parsePouch({ id: "p1" })).toBeUndefined();
    expect(parseReports("x")).toBeUndefined();
  });
});
