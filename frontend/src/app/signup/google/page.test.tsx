// @vitest-environment jsdom
import { act, useLayoutEffect } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider, useSession } from "@/features/session/session-provider";
import { api, ApiError } from "@/lib/api";

import GoogleSignupPage from "./page";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const PENDING = { email: "new@gmail.com", name: "Kim Seoyun", expiresAt: "2099-01-01T00:00:00Z" };
const LOGGED_IN = {
  user: {
    userId: "u1",
    email: PENDING.email,
    nickname: null,
    provider: "GOOGLE",
    createdAt: "2026-11-10T00:00:00Z",
  },
  csrfToken: "csrf",
};

let session: ReturnType<typeof useSession>;
let root: Root;
let element: HTMLDivElement;
function Probe() {
  const value = useSession();
  useLayoutEffect(() => {
    session = value;
  });
  return null;
}
const text = () => element.textContent ?? "";
const button = (label: string) => {
  const found = [...element.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
  if (!found) throw new Error(`${label} 버튼이 없습니다`);
  return found;
};
const input = (id: string) => element.querySelector<HTMLInputElement>(`#${id}`)!;
/** React가 바뀐 값을 알아채도록 원래 setter로 넣고 input 이벤트를 보낸다 */
const type = async (id: string, value: string) => {
  const el = input(id);
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () => {
    setter.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
};
const submit = async () => {
  await act(async () => {
    element
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
};
const render = async () => {
  await act(async () => {
    root.render(
      <SessionProvider seed={{ pouch: [], reports: [] }}>
        <Probe />
        <GoogleSignupPage />
      </SessionProvider>,
    );
  });
};

beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
    removeItem: (key: string) => saved.delete(key),
    clear: () => saved.clear(),
  });
  vi.clearAllMocks();
  // 가입 전이라 내 계정 조회는 401, 가입 대기 조회는 성공
  vi.spyOn(api, "get").mockImplementation(async (path: string) => {
    if (path === "/v1/users/oauth/google/signup") return PENDING;
    throw new ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.");
  });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Google 첫 가입", () => {
  it("가입 대기의 이메일을 고정으로 보여 주고, 규칙에 맞는 Google 이름은 이름 칸에 채운다", async () => {
    await render();
    expect(input("gs-email").value).toBe(PENDING.email);
    expect(input("gs-email").readOnly).toBe(true);
    expect(input("gs-name").value).toBe("Kim Seoyun");
  });

  it("가입 대기가 만료됐으면 로그인 화면에서 다시 시작하도록 보낸다", async () => {
    vi.mocked(api.get).mockImplementation(async (path: string) => {
      if (path === "/v1/users/oauth/google/signup")
        throw new ApiError(410, "USERS_GOOGLE_SIGNUP_EXPIRED", "가입 시간이 지났습니다.");
      throw new ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.");
    });
    await render();
    expect(router.replace).toHaveBeenCalledWith("/login?error=USERS_GOOGLE_SIGNUP_EXPIRED");
  });

  it("약관에 동의하면 추가 정보와 약관을 보내 가입하고, 바로 로그인해 온보딩으로 간다", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue(LOGGED_IN);
    await render();
    await type("gs-nickname", "seoyun_1");
    await act(async () => button("전체 동의").click());
    await submit();
    expect(post).toHaveBeenCalledWith(
      "/v1/users/oauth/google/signup",
      expect.objectContaining({
        body: expect.objectContaining({
          nickname: "seoyun_1",
          name: "Kim Seoyun",
          agreements: expect.arrayContaining([
            expect.objectContaining({ type: "TERMS", agreed: true }),
            expect.objectContaining({ type: "MARKETING", agreed: true }),
          ]),
        }),
      }),
    );
    expect(session.state.loggedIn).toBe(true);
    expect(session.state.email).toBe(PENDING.email);
    expect(router.replace).toHaveBeenCalledWith("/onboarding");
  });

  it("그사이 같은 이메일 계정이 생겼으면 로그인 화면의 계정 안내로 보낸다", async () => {
    vi.spyOn(api, "post").mockRejectedValue(
      new ApiError(409, "USERS_ACCOUNT_LINK_REQUIRED", "같은 이메일로 가입된 계정이 있습니다."),
    );
    await render();
    await act(async () => button("전체 동의").click());
    await submit();
    expect(router.replace).toHaveBeenCalledWith("/login?error=USERS_ACCOUNT_LINK_REQUIRED");
  });

  it("입력 오류는 해당 칸 아래에 보여 주고 폼 아래 안내는 띄우지 않는다", async () => {
    vi.spyOn(api, "post").mockRejectedValue(
      new ApiError(400, "VALIDATION_FAILED", "입력값이 올바르지 않습니다.", [
        { field: "nickname", reason: "이미 사용 중인 닉네임입니다." },
      ]),
    );
    await render();
    await act(async () => button("전체 동의").click());
    await submit();
    expect(text()).toContain("이미 사용 중인 닉네임입니다.");
    expect(text()).not.toContain("입력값이 올바르지 않습니다.");
    expect(router.replace).not.toHaveBeenCalled();
  });
});
