import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";

import { GuideStore } from "./guide-store";

const A = "a0000000-0000-4000-8000-000000000001";
const B = "a0000000-0000-4000-8000-000000000002";
const response = (guideId = A, guideVersion = 1) => ({
  guideId,
  guideVersion,
  stepCount: 1,
  steps: [{ stepId: "s1", order: 1, type: "GUIDE", part: "blush" }],
});
const deferred = () => {
  let resolve!: (value: unknown) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<unknown>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
afterEach(() => vi.useRealTimers());

describe("공유 가이드 조회", () => {
  it("소비자가 여럿이어도 진행 중 요청은 공유하고 구독 해제만으로 취소하지 않는다", async () => {
    const wait = deferred();
    const fetch = vi.fn(() => wait.promise);
    const store = new GuideStore(fetch);
    const off = store.subscribe(vi.fn());
    store.activate("run-a", A);
    const first = store.retry();
    expect(store.retry()).toBe(first);
    off();
    wait.resolve(response());
    expect(await first).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().load.status).toBe("ready");
  });
  it.each(["resolve", "reject"] as const)(
    "취소를 무시한 A의 늦은 %s가 B를 덮어쓰지 않는다",
    async (finish) => {
      const a = deferred();
      const fetch = vi.fn().mockReturnValueOnce(a.promise).mockResolvedValue(response(B));
      const store = new GuideStore(fetch);
      store.activate("run-a", A);
      const first = store.retry();
      await Promise.resolve();
      store.activate("run-b", B);
      await store.retry();
      if (finish === "resolve") a.resolve(response(A));
      else a.reject(new ApiError(404, "NOT_FOUND", "없음"));
      await first;
      expect(store.getSnapshot()).toMatchObject({
        key: "run-b",
        load: { status: "ready", guide: { guideId: B } },
      });
    },
  );
  it("동일 guideId의 새 실행에서도 이전 버전과 요청을 재사용하지 않는다", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response(A, 1))
      .mockResolvedValueOnce(response(A, 2));
    const store = new GuideStore(fetch);
    store.activate("first", A);
    await store.retry();
    store.activate("second", A);
    await store.retry();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().load).toMatchObject({ status: "ready", guide: { guideVersion: 2 } });
  });
  it.each(["404", "version"])(
    "진행 중 %s는 실행을 무효화하고 재시도로 부활시키지 않는다",
    async (kind) => {
      const fetch = vi.fn().mockResolvedValueOnce(response());
      if (kind === "404") fetch.mockRejectedValueOnce(new ApiError(404, "NOT_FOUND", "없음"));
      else fetch.mockResolvedValueOnce(response(A, 2));
      const store = new GuideStore(fetch);
      store.activate("run", A);
      await store.retry();
      expect(await store.retry()).toBe(false);
      expect(store.getSnapshot().load.status).toBe("invalidated");
      expect(await store.retry()).toBe(false);
      expect(fetch).toHaveBeenCalledTimes(2);
    },
  );
  it("일시적 오류 후에는 같은 스냅샷을 유지하고 재검증 성공으로 복구한다", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response())
      .mockRejectedValueOnce(new ApiError(503, "SERVICE_UNAVAILABLE", "잠시 후 다시"))
      .mockResolvedValue(response());
    const store = new GuideStore(fetch);
    store.activate("run", A);
    await store.retry();
    const before = store.getSnapshot().load;
    await store.retry();
    expect(store.getSnapshot().load).toMatchObject({ status: "ready", error: "잠시 후 다시" });
    await store.retry();
    const after = store.getSnapshot().load;
    expect(after).toMatchObject({ status: "ready", error: null, checking: false });
    if (before.status === "ready" && after.status === "ready")
      expect(after.guide).toBe(before.guide);
  });
  it("무효 ID는 요청하지 않고 응답 ID 불일치는 계약 오류로 막는다", async () => {
    const fetch = vi.fn().mockResolvedValue(response(B));
    const store = new GuideStore(fetch);
    store.activate("invalid", "bad");
    expect(store.getSnapshot().load.status).toBe("invalidId");
    expect(fetch).not.toHaveBeenCalled();
    store.activate("run", A);
    await store.retry();
    expect(store.getSnapshot().load.status).toBe("error");
  });
  it("시간 초과와 종료 취소는 요청·타이머를 정리하고 다음 재시도가 가능하다", async () => {
    vi.useFakeTimers();
    const store = new GuideStore(
      vi.fn(() => new Promise(() => {})),
      100,
    );
    store.activate("run", A);
    const request = store.retry();
    await vi.advanceTimersByTimeAsync(100);
    expect(await request).toBe(false);
    expect(store.getSnapshot().load.status).toBe("error");
    const retry = store.retry();
    store.clear();
    await retry;
    expect(store.getSnapshot().key).toBe("");
    expect(vi.getTimerCount()).toBe(0);
  });
  it("401은 로그인 필요 상태이며 이전 요청이 세션 종료 후 되살아나지 않는다", async () => {
    const fetch = vi.fn().mockRejectedValue(new ApiError(401, "UNAUTHORIZED", "로그인 필요"));
    const store = new GuideStore(fetch);
    store.activate("run", A);
    await store.retry();
    expect(store.getSnapshot().load.status).toBe("login");
    store.clear();
    expect(store.getSnapshot().key).toBe("");
  });
});
