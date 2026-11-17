// @vitest-environment jsdom
import { act, useEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "./auth";
import { useDevice } from "./device";
import { SessionProvider, useSession, useSessionActions } from "./session-provider";
import { STORAGE_KEYS } from "./storage";

// 내 계정 조회는 끝나지 않게 두어 저장값만으로 시작한다
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, get: vi.fn(() => new Promise(() => {})) } };
});

type Handle = {
  actions: ReturnType<typeof useSessionActions>;
  update: ReturnType<typeof useSession>["update"];
};
const handle: { current: Handle | null } = { current: null };

function Probe() {
  const auth = useAuth();
  const device = useDevice();
  const actions = useSessionActions();
  const { update } = useSession();
  useEffect(() => {
    handle.current = { actions, update };
  });
  return (
    <div
      data-expired={String(auth.sessionExpired)}
      data-logged={String(auth.loggedIn)}
      data-onboarded={String(device.onboarded)}
    />
  );
}

let root: Root;
let element: HTMLDivElement;
const attr = (name: string) => element.querySelector("div")?.getAttribute(`data-${name}`);

const mount = async () => {
  await act(async () =>
    root.render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    ),
  );
};

beforeEach(() => {
  localStorage.clear();
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  handle.current = null;
});

describe("세션 상태", () => {
  it("로그아웃 직후 들어온 401은 만료 안내로 남기지 않는다", async () => {
    localStorage.setItem(
      STORAGE_KEYS.auth,
      JSON.stringify({ loggedIn: true, email: "a@b.c", nickname: "", sessionExpired: false }),
    );
    await mount();
    expect(attr("logged")).toBe("true");

    // 다시 그리기 전에 만료 응답이 이어서 들어오는 경우
    await act(async () => {
      handle.current!.actions.signOut();
      handle.current!.actions.expireSession();
    });
    expect(attr("logged")).toBe("false");
    expect(attr("expired")).toBe("false");
  });

  it("로그인한 채 만료되면 만료 안내를 남긴다", async () => {
    localStorage.setItem(
      STORAGE_KEYS.auth,
      JSON.stringify({ loggedIn: true, email: "a@b.c", nickname: "", sessionExpired: false }),
    );
    await mount();
    await act(async () => handle.current!.actions.expireSession());
    expect(attr("logged")).toBe("false");
    expect(attr("expired")).toBe("true");
  });

  it("update로 온보딩 완료를 되돌릴 수 있다", async () => {
    localStorage.setItem(STORAGE_KEYS.device, JSON.stringify({ onboarded: true, tutSeen: true }));
    await mount();
    expect(attr("onboarded")).toBe("true");

    await act(async () => handle.current!.update({ onboarded: false }));
    expect(attr("onboarded")).toBe("false");
  });
});
