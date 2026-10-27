import type { ApiErrorBody, Health, User } from "./types";

/** 모의 응답 시나리오. BE 없이 화면을 만들 때 성공·오류 흐름을 골라 확인한다. */
export type MockScenario = "success" | "error";

export const MOCK_SCENARIOS: readonly MockScenario[] = ["success", "error"];

type MockResult = { status: number; body?: unknown };

interface MockRoute {
  method: string;
  /** 쿼리를 뺀 경로 */
  path: RegExp;
  success: () => MockResult;
  error: () => MockResult;
}

// 응답을 늦게 주어 로딩 표시와 요청 취소를 확인할 수 있게 한다.
const DELAY_MS = 400;

const error = (status: number, body: ApiErrorBody): MockResult => ({ status, body });

// 상태·코드·메시지는 BE GlobalExceptionHandler·SecurityConfig·회원가입 서비스가 실제로 돌려주는 값이다.
// 모의 응답은 요청 본문을 보지 않고 시나리오대로만 답한다.
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
    path: /^\/v1\/users$/,
    success: () => ({
      status: 201,
      body: {
        userId: "usr_mock_01",
        email: "mock@example.com",
        createdAt: "2026-10-27T00:00:00Z",
      } satisfies User,
    }),
    error: () =>
      error(400, {
        code: "VALIDATION_FAILED",
        message: "입력값이 올바르지 않습니다.",
        details: [{ field: "passwordConfirm", reason: "비밀번호와 일치하지 않습니다." }],
      }),
  },
  {
    // 로그인이 필요한 변경 요청 예시. CSRF 토큰이 없거나 맞지 않으면 인증 확인보다 먼저 403으로 막힌다.
    // BE 미구현이라 로그인 이슈에서 경로를 확정한다. 실제 서버도 CSRF 검사가 먼저라 403 CSRF_INVALID가 나온다.
    method: "DELETE",
    path: /^\/v1\/users\/me\/sessions\/current$/,
    success: () => ({ status: 204 }),
    error: () =>
      error(403, { code: "CSRF_INVALID", message: "요청 보안 토큰이 유효하지 않습니다." }),
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
    ? error(404, { code: "NOT_FOUND", message: "요청한 리소스를 찾을 수 없습니다." })
    : scenario === "error"
      ? route.error()
      : route.success();

  if (result.body === undefined) return new Response(null, { status: result.status });
  return new Response(JSON.stringify(result.body), {
    status: result.status,
    headers: { "Content-Type": "application/json" },
  });
}
