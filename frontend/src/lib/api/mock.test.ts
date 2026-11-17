import { describe, expect, it, vi } from "vitest";

import { mockFetch } from "./mock";
import type { PouchList } from "./types";

async function response(path: string, method = "GET") {
  vi.useFakeTimers();
  const pending = mockFetch("success", method, path);
  await vi.advanceTimersByTimeAsync(400);
  const result = await pending;
  vi.useRealTimers();
  return result;
}

describe("모의 파우치와 가이드 매칭", () => {
  it("준비된 파우치 제품을 모두 돌려준다", async () => {
    const result = await response("/v1/users/me/pouch-items");
    const body = (await result.json()) as PouchList;

    expect(body.items).toHaveLength(6);
    expect(body.items.map((item) => item.pouchItemId)).toEqual([
      "p1",
      "p2",
      "p3",
      "p4",
      "p5",
      "p6",
    ]);
  });

  it("게이지가 있는 립 라인 단계에 모의 립 제품을 대체 제품으로 연결한다", async () => {
    const result = await response("/v1/users/me/guide-matches", "POST");
    const body = (await result.json()) as {
      steps: { stepId: string; result: string; candidates: { pouchItemId: string }[] }[];
    };

    expect(body.steps.find((step) => step.stepId === "s17")).toMatchObject({
      result: "SUBSTITUTE",
      candidates: [{ pouchItemId: "p6" }],
    });
  });
});
