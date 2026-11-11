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
  VideoSearchItem,
  VideoSearchPage,
  VideoSelection,
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
// 영상 검색·선택 모의 응답. guideId는 mocks/mock-guide-api의 MOCK_GUIDE_ID(샘플 영상 가이드)와 같다
const MOCK_VIDEO: VideoSearchItem = {
  youtubeVideoId: "VxAXD6PP76I",
  title: "피부 좋아 보인다는 말 듣는 데일리 메이크업",
  channelTitle: "뷰티 크리에이터 A",
  durationSeconds: 760,
  thumbnailUrl: "https://i.ytimg.com/vi/VxAXD6PP76I/hqdefault.jpg",
  viewCount: 180_345,
  publishedAt: "2026-10-23T09:00:00Z",
  guideId: "a0000000-0000-4000-8000-000000000001",
  guideAvailable: true,
};
const NO_GUIDE = { guideId: null, guideAvailable: false } as const;

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
    // 요청 본문(guideId)을 보지 않으므로 단계 결과 없이 답한다. 화면은 모든 단계를 비교 기준 없음으로 본다
    method: "POST",
    path: /^\/v1\/users\/me\/guide-matches$/,
    success: () => ({ status: 201, body: { matchId: "mock-match", guideId: "", steps: [] } }),
    error: () => NOT_FOUND(),
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
  {
    // 검색어와 상관없이 같은 두 영상. 첫 영상은 모의 가이드(mocks/mock-guide-api의 샘플 영상 가이드)와 이어진다
    method: "GET",
    path: /^\/v1\/videos\/search$/,
    success: () => ({
      status: 200,
      body: {
        items: [
          MOCK_VIDEO,
          {
            ...MOCK_VIDEO,
            youtubeVideoId: "eoNi1sl-5RQ",
            title: "10분 완성 코랄 블러셔 메이크업",
            thumbnailUrl: "https://i.ytimg.com/vi/eoNi1sl-5RQ/hqdefault.jpg",
            ...NO_GUIDE,
          },
        ],
        nextPageToken: null,
        size: 20,
      } satisfies VideoSearchPage,
    }),
    error: () =>
      error(503, {
        code: "VIDEO_SEARCH_UNAVAILABLE",
        message: "지금은 영상 검색을 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
      }),
  },
  {
    // 모의 응답은 요청 본문을 보지 않아, 어느 영상을 골라도 가이드가 있는 영상으로 답한다
    method: "POST",
    path: /^\/v1\/videos$/,
    success: () => ({
      status: 200,
      body: {
        ...MOCK_VIDEO,
        videoId: "b0000000-0000-4000-8000-000000000001",
        chapters: [
          { startSeconds: 202, label: "파운데이션" },
          { startSeconds: 242, label: "크림 블러셔" },
          { startSeconds: 319, label: "언더 아이라인" },
        ],
        analysisJobId: null,
        reviewStatus: "APPROVED",
      } satisfies VideoSelection,
    }),
    error: () =>
      error(409, {
        code: "VIDEO_UNSUPPORTED_FOR_ANALYSIS",
        message: "분석할 수 없는 영상입니다. 크리에이티브 커먼즈(CC BY) 영상만 분석할 수 있습니다.",
      }),
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
