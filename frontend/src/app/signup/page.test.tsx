// @vitest-environment jsdom
import { act, type ComponentType } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as Api from "@/lib/api";

const router = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

let root: Root;
let element: HTMLDivElement;
let SignupPage: ComponentType;
let api: typeof Api.api;
let ApiError: typeof Api.ApiError;
const text = () => element.textContent ?? "";
const button = (label: string) => {
  const found = [...element.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
  if (!found) throw new Error(`${label} 버튼이 없습니다`);
  return found;
};
const type = async (id: string, value: string) => {
  const el = element.querySelector<HTMLInputElement>(`#${id}`)!;
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
const fillRequired = async () => {
  await type("su-email", "new@example.com");
  await act(async () => button("중복 확인").click());
  await type("su-pw", "abcd1234!");
  await type("su-pw2", "abcd1234!");
  await act(async () => button("전체 동의").click());
};

beforeEach(async () => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  const saved = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => saved.get(key) ?? null,
    setItem: (key: string, value: string) => saved.set(key, value),
    removeItem: (key: string) => saved.delete(key),
    clear: () => saved.clear(),
  });
  vi.stubEnv("NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION", "");
  vi.resetModules();
  SignupPage = (await import("./page")).default;
  ({ api, ApiError } = await import("@/lib/api"));
  const { SessionProvider } = await import("@/domain/session/session-provider");
  vi.clearAllMocks();
  vi.spyOn(api, "get").mockRejectedValue(new ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다."));
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
  await act(async () => {
    root.render(
      <SessionProvider seed={{ pouch: [], reports: [] }}>
        <SignupPage />
      </SessionProvider>,
    );
  });
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("이메일 회원가입 (추가 정보·약관 공용 입력)", () => {
  it("추가 정보와 약관 4개를 이메일·비밀번호와 함께 보낸다", async () => {
    const post = vi
      .spyOn(api, "post")
      .mockImplementation(async (path: string) =>
        path === "/v1/users/email-availability"
          ? { email: "new@example.com", available: true }
          : { userId: "u1" },
      );
    await fillRequired();
    await type("su-nickname", "seoyun_1");
    await submit();
    expect(post).toHaveBeenCalledWith(
      "/v1/users/signup",
      expect.objectContaining({
        body: expect.objectContaining({
          email: "new@example.com",
          password: "abcd1234!",
          passwordConfirm: "abcd1234!",
          nickname: "seoyun_1",
          agreements: [
            expect.objectContaining({ type: "TERMS", agreed: true }),
            expect.objectContaining({ type: "PRIVACY", agreed: true }),
            expect.objectContaining({ type: "AGE_OVER_14", agreed: true }),
            expect.objectContaining({ type: "MARKETING", agreed: true }),
          ],
        }),
      }),
    );
    expect(router.replace).toHaveBeenCalledWith("/login?signup=done&email=new%40example.com");
  });

  it("필수 약관이 빠졌다는 응답은 약관 칸에, 선택 항목 입력 오류는 그 칸 아래에 보여 준다", async () => {
    vi.spyOn(api, "post").mockImplementation(async (path: string) => {
      if (path === "/v1/users/email-availability")
        return { email: "new@example.com", available: true };
      throw new ApiError(400, "VALIDATION_FAILED", "입력값이 올바르지 않습니다.", [
        { field: "phone", reason: "휴대폰 번호 형식이 아닙니다." },
      ]);
    });
    await fillRequired();
    await submit();
    expect(text()).toContain("휴대폰 번호 형식이 아닙니다.");

    vi.mocked(api.post).mockRejectedValueOnce(
      new ApiError(400, "USERS_REQUIRED_AGREEMENT_MISSING", "필수 약관에 동의해 주세요."),
    );
    await submit();
    expect(text()).toContain("약관이 새로 바뀌었어요");
    expect(router.replace).not.toHaveBeenCalled();
  });
});
