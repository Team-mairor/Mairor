import type {
  ApiErrorBody,
  CodeSent,
  EmailAvailability,
  EmailVerified,
  GoogleSignupPending,
  Health,
  LoginResponse,
  PasswordResetVerified,
  User,
} from "./types";

/** 모의 응답 시나리오. BE 없이 화면을 만들 때 성공·오류 흐름을 골라 확인한다. */
export type MockScenario = "success" | "error";

export const MOCK_SCENARIOS: readonly MockScenario[] = ["success", "error"];

type MockResult = { status: number; body?: unknown };

interface MockRoute {
  method: string;
  /** 쿼리를 뺀 경로 */
  path: RegExp;
  /** path는 쿼리를 뺀 요청 경로. 경로에 든 ID로 답을 고를 때 쓴다 */
  success: (path: string) => MockResult | Promise<MockResult>;
  error: () => MockResult;
}

// 응답을 늦게 주어 로딩 표시와 요청 취소를 확인할 수 있게 한다.
const DELAY_MS = 400;

const error = (status: number, body: ApiErrorBody): MockResult => ({ status, body });

const USER: User = {
  userId: "usr_mock_01",
  email: "mock@example.com",
  nickname: null,
  provider: "LOCAL",
  createdAt: "2026-10-27T00:00:00Z",
};
const LOGGED_IN: LoginResponse = { user: USER, csrfToken: "mock-csrf-token" };
const CODE_SENT: CodeSent = { expiresInSeconds: 600, resendAvailableInSeconds: 60 };
const TOKEN_EXPIRES_AT = "2099-01-01T00:00:00Z";

// 상태·코드·메시지는 BE GlobalExceptionHandler·SecurityConfig·회원 서비스가 실제로 돌려주는 값이다.
// 모의 응답은 요청 본문을 보지 않고 시나리오대로만 답한다.
const NOT_FOUND = () =>
  error(404, { code: "NOT_FOUND", message: "요청한 리소스를 찾을 수 없습니다." });

const ROUTES: MockRoute[] = [
  {
    method: "GET",
    path: /^\/health$/,
    success: () => ({ status: 200, body: { status: "UP" } satisfies Health }),
    error: () =>
      error(500, { code: "INTERNAL_ERROR", message: "서버에서 예기치 않은 오류가 발생했습니다." }),
  },
  {
    // 회원가입은 세션이 없어 CSRF 토큰 대신 허용 Origin으로 검사한다.
    method: "POST",
    path: /^\/v1\/users\/signup$/,
    success: () => ({
      status: 201,
      body: USER,
    }),
    error: () =>
      error(400, {
        code: "VALIDATION_FAILED",
        message: "입력값이 올바르지 않습니다.",
        details: [{ field: "passwordConfirm", reason: "비밀번호와 일치하지 않습니다." }],
      }),
  },
  {
    method: "GET",
    path: /^\/v1\/users\/oauth\/google\/signup$/,
    success: () => ({
      status: 200,
      body: {
        email: "mock.google@gmail.com",
        name: "Mock User",
        expiresAt: TOKEN_EXPIRES_AT,
      } satisfies GoogleSignupPending,
    }),
    error: () =>
      error(410, {
        code: "USERS_GOOGLE_SIGNUP_EXPIRED",
        message: "가입 시간이 지났습니다. Google 로 다시 시작해 주세요.",
      }),
  },
  {
    // Google 가입도 세션이 없어 CSRF 토큰 대신 허용 Origin으로 검사한다.
    method: "POST",
    path: /^\/v1\/users\/oauth\/google\/signup$/,
    success: () => ({
      status: 201,
      body: {
        user: { ...USER, email: "mock.google@gmail.com", provider: "GOOGLE" },
        csrfToken: "mock-csrf-token",
      } satisfies LoginResponse,
    }),
    error: () =>
      error(409, {
        code: "USERS_ACCOUNT_LINK_REQUIRED",
        message: "같은 이메일로 가입된 계정이 있습니다. 이메일로 로그인해 주세요.",
      }),
  },
  {
    method: "POST",
    path: /^\/v1\/users\/login$/,
    success: () => ({ status: 200, body: LOGGED_IN }),
    error: () =>
      error(401, {
        code: "USERS_INVALID_CREDENTIALS",
        message: "이메일 또는 비밀번호를 확인해 주세요.",
      }),
  },
  {
    method: "GET",
    path: /^\/v1\/users\/me$/,
    success: () => ({ status: 200, body: LOGGED_IN }),
    error: () => error(401, { code: "UNAUTHORIZED", message: "로그인이 필요합니다." }),
  },
  {
    method: "POST",
    path: /^\/v1\/users\/email-availability$/,
    success: () => ({
      status: 200,
      body: { email: USER.email, available: true } satisfies EmailAvailability,
    }),
    error: () =>
      error(429, { code: "USERS_EMAIL_CHECK_RATE_LIMITED", message: "요청 한도를 초과했습니다." }),
  },
  {
    method: "POST",
    path: /^\/v1\/users\/email-verification$/,
    success: () => ({ status: 202, body: CODE_SENT }),
    error: () =>
      error(409, { code: "USERS_EMAIL_DUPLICATE", message: "이미 가입된 이메일입니다." }),
  },
  {
    method: "POST",
    path: /^\/v1\/users\/email-verification\/verification$/,
    success: () => ({
      status: 200,
      body: {
        verificationToken: "mock-verification-token",
        expiresAt: TOKEN_EXPIRES_AT,
      } satisfies EmailVerified,
    }),
    error: () =>
      error(400, { code: "USERS_EMAIL_CODE_INVALID", message: "인증번호가 일치하지 않습니다." }),
  },
  {
    method: "POST",
    path: /^\/v1\/users\/password-reset$/,
    success: () => ({ status: 202, body: CODE_SENT }),
    error: () =>
      error(503, {
        code: "USERS_RESET_SEND_FAILED",
        message: "비밀번호 재설정 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.",
      }),
  },
  {
    method: "POST",
    path: /^\/v1\/users\/password-reset\/verification$/,
    success: () => ({
      status: 200,
      body: {
        resetToken: "mock-reset-token",
        expiresAt: TOKEN_EXPIRES_AT,
      } satisfies PasswordResetVerified,
    }),
    error: () =>
      error(400, { code: "USERS_RESET_CODE_INVALID", message: "인증번호가 일치하지 않습니다." }),
  },
  {
    method: "PUT",
    path: /^\/v1\/users\/password-reset\/password$/,
    success: () => ({ status: 204 }),
    error: () =>
      error(410, {
        code: "USERS_RESET_TOKEN_EXPIRED",
        message: "재설정 시간이 지났거나 이미 사용한 요청입니다. 인증번호를 다시 받아 주세요.",
      }),
  },
  {
    // 로그인이 필요한 변경 요청 예시. CSRF 토큰이 없거나 맞지 않으면 인증 확인보다 먼저 403으로 막힌다.
    method: "POST",
    path: /^\/v1\/users\/logout$/,
    success: () => ({ status: 204 }),
    error: () =>
      error(403, { code: "CSRF_INVALID", message: "요청 보안 토큰이 유효하지 않습니다." }),
  },
  {
    // 모의 가이드 ID(mocks/mock-guide-api)만 답하고, 그 밖의 ID는 서버처럼 404다
    method: "GET",
    path: /^\/v1\/guides\/[^/]+$/,
    success: async (path) => {
      // 모의 가이드는 이 경로를 부를 때만 불러와, 다른 화면 번들에 목업 단계가 실리지 않게 한다
      const { MOCK_LOGIN_REQUIRED_GUIDE_ID, mockGuide } = await import("@/mocks/mock-guide-api");
      const guideId = decodeURIComponent(path.slice(path.lastIndexOf("/") + 1));
      if (guideId === MOCK_LOGIN_REQUIRED_GUIDE_ID)
        return error(401, { code: "UNAUTHORIZED", message: "로그인이 필요합니다." });
      const guide = await mockGuide(guideId);
      return guide ? { status: 200, body: guide } : NOT_FOUND();
    },
    error: () =>
      error(500, { code: "INTERNAL_ERROR", message: "서버에서 예기치 않은 오류가 발생했습니다." }),
  },
];

function wait(ms: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal?.reason);
    };
    // 화면 단위로 컨트롤러 하나를 같이 쓰면 요청마다 리스너가 쌓이므로, 끝나면 뗀다.
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/** fetch 대신 모의 응답을 Response로 돌려준다. 실제 응답과 같은 경로로 처리된다. */
export async function mockFetch(
  scenario: MockScenario,
  method: string,
  path: string,
  signal?: AbortSignal,
): Promise<Response> {
  await wait(DELAY_MS, signal);
  const route = ROUTES.find((r) => r.method === method && r.path.test(path));
  const result: MockResult = !route
    ? NOT_FOUND()
    : scenario === "error"
      ? route.error()
      : await route.success(path);

  if (result.body === undefined) return new Response(null, { status: result.status });
  return new Response(JSON.stringify(result.body), {
    status: result.status,
    headers: { "Content-Type": "application/json" },
  });
}
