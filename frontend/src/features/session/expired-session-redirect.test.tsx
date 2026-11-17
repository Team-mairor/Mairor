// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const session = vi.hoisted(() => ({
  sessionChecked: true,
  state: { loggedIn: true, sessionExpired: false },
}));
const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));

vi.mock("./session-provider", () => ({ useSession: () => session }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

import { ExpiredSessionRedirect } from "./expired-session-redirect";

let root: Root;
let element: HTMLDivElement;

function render() {
  act(() => root.render(<ExpiredSessionRedirect />));
}

describe("ExpiredSessionRedirect", () => {
  beforeEach(() => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    element = document.createElement("div");
    document.body.append(element);
    root = createRoot(element);
    router.replace.mockClear();
  });

  afterEach(() => {
    act(() => root.unmount());
    element.remove();
  });

  it("로그인이 끊기면(다른 기기 로그인 등) 로그인 화면으로 보낸다", () => {
    session.sessionChecked = true;
    session.state = { loggedIn: false, sessionExpired: true };
    render();
    expect(router.replace).toHaveBeenCalledWith("/login?expired=basic");
  });

  it("로그인 중이면 그대로 둔다", () => {
    session.sessionChecked = true;
    session.state = { loggedIn: true, sessionExpired: false };
    render();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("로그인 확인이 끝나기 전에는 옮기지 않는다", () => {
    session.sessionChecked = false;
    session.state = { loggedIn: false, sessionExpired: true };
    render();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("직접 로그아웃해 만료 표시가 없으면 옮기지 않는다", () => {
    session.sessionChecked = true;
    session.state = { loggedIn: false, sessionExpired: false };
    render();
    expect(router.replace).not.toHaveBeenCalled();
  });
});
