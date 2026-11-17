// @vitest-environment jsdom
import { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api";

import { SessionProvider, useSessionActions } from "./session-provider";
import { useTour } from "./tour";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let session: ReturnType<typeof useSessionActions>;
let tour: ReturnType<typeof useTour>;
function Probe() {
  const value = { session: useSessionActions(), tour: useTour("home") };
  useLayoutEffect(() => {
    ({ session, tour } = value);
  });
  return null;
}

let root: Root;
const user = (email: string) => ({ email, nickname: "" });

beforeEach(async () => {
  localStorage.clear();
  vi.spyOn(api, "get").mockRejectedValue(new ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다."));
  root = createRoot(document.createElement("div"));
  await act(async () =>
    root.render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    ),
  );
});

afterEach(() => {
  act(() => root.unmount());
  vi.restoreAllMocks();
});

describe("useTour", () => {
  it("로그인할 때마다 화면 안내를 다시 보여 주고, 같은 로그인 안에서는 한 번만 보여 준다", () => {
    act(() => session.signIn(user("a@example.com")));
    expect(tour.show).toBe(true);

    act(() => tour.done());
    expect(tour.show).toBe(false);
    // 로그인한 채 세션을 다시 확인해도 다시 띄우지 않는다
    act(() => session.signIn(user("a@example.com")));
    expect(tour.show).toBe(false);

    act(() => session.signOut());
    act(() => session.signIn(user("a@example.com")));
    expect(tour.show).toBe(true);
  });

  it("세션이 만료된 뒤 다시 로그인해도 안내를 보여 준다", () => {
    act(() => session.signIn(user("a@example.com")));
    act(() => tour.done());
    act(() => session.expireSession());
    act(() => session.signIn(user("a@example.com")));
    expect(tour.show).toBe(true);
  });
});
