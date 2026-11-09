import { MOCK_SCENARIOS, mockFetch, type MockScenario } from "./mock";
import type { ApiErrorBody, FieldError, LoginResponse } from "./types";

// 프론트와 API는 같은 Origin에 배포하고 리버스 프록시가 /api를 BE로 넘긴다 (BE context-path가 /api).
// 세션 쿠키가 같은 Origin에만 실리므로 다른 도메인 주소는 지원하지 않는다. 빈 값이면 기본값을 쓴다.
const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL || "/api").replace(/\/$/, "");

/** 서버에 닿지 못했을 때(네트워크 끊김 등)의 code */
export const NETWORK_ERROR = "NETWORK_ERROR";
/** signal에 AbortSignal.timeout()을 넣어 시간이 지나 끊겼을 때의 code */
export const TIMEOUT = "TIMEOUT";
/** 응답이 공통 형식이 아닐 때(프록시 오류 페이지, JSON이 아닌 성공 응답 등)의 code */
export const UNEXPECTED_RESPONSE = "UNEXPECTED_RESPONSE";

/** 실패한 API 요청. 공통 오류 응답의 code·message·details를 그대로 담는다. */
export class ApiError extends Error {
  constructor(
    /** HTTP 상태. 서버에 닿지 못했으면 0 */
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: FieldError[] = [],
    /** 429일 때 Retry-After(초) */
    readonly retryAfterSeconds: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// README "오류 코드별 화면 처리" 표의 코드. 이 코드의 message만 사용자에게 그대로 보여 준다 (USERS_*는 모두 해당).
const SHOWN_CODES = new Set([
  "VALIDATION_FAILED",
  "UNAUTHORIZED",
  "CSRF_INVALID",
  "FORBIDDEN",
  "NOT_FOUND",
  "CONFLICT",
  "TOO_MANY_REQUESTS",
  "SERVICE_UNAVAILABLE",
  "POUCH_DUPLICATE",
  NETWORK_ERROR,
  TIMEOUT,
]);

/** 화면에 보여 줄 오류 문구. 표에 없는 코드(INTERNAL_ERROR·UNEXPECTED_RESPONSE 등)는 message 대신 공통 문구를 쓴다. */
export function errorMessage(e: unknown) {
  return e instanceof ApiError && (e.code.startsWith("USERS_") || SHOWN_CODES.has(e.code))
    ? e.message
    : "잠시 후 다시 시도해 주세요.";
}

/** 화면에 보여 줄 실패 문구. 입력 오류면 첫 칸의 사유를 쓴다 (입력 칸이 하나인 요청용) */
export function failText(e: unknown) {
  return e instanceof ApiError && e.code === "VALIDATION_FAILED" && e.details[0]
    ? e.details[0].reason
    : errorMessage(e);
}

let csrfToken: string | null = null;

/**
 * CSRF 토큰을 넣어 두면 변경 요청에 X-CSRF-TOKEN(스프링 시큐리티 기본 헤더)으로 붙인다. 로그아웃하면 null.
 * 로그인·내 계정 조회 응답의 csrfToken을 고치지 않고 그대로 넣는다 (서버가 마스킹한 값이라 그 값으로 검사한다).
 * 토큰이 없거나 맞지 않는 변경 요청은 403 CSRF_INVALID이고, request()가 내 계정 조회로 토큰을 다시 받아 한 번만 다시 보낸다.
 * 회원가입·로그인은 세션이 없어 토큰 대신 허용 Origin으로 검사한다 (허용되지 않으면 403 FORBIDDEN).
 */
export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

function parseScenario(value: string | undefined): MockScenario | null {
  return MOCK_SCENARIOS.find((s) => s === value) ?? null;
}

// NEXT_PUBLIC_API_MOCK=success|error 이면 BE 대신 모의 응답을 쓴다.
// .env.local에 값이 남은 채로 배포본이 가짜 데이터를 보여 주지 않도록 운영 빌드(next build)에서는 무시한다.
const DEFAULT_MOCK =
  process.env.NODE_ENV === "production" ? null : parseScenario(process.env.NEXT_PUBLIC_API_MOCK);

type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  /** 값이 null·undefined인 항목은 보내지 않는다. */
  query?: Record<string, QueryValue>;
  /** FormData는 multipart로, Blob·URLSearchParams는 그대로 보내고 그 밖의 값은 JSON으로 보낸다. */
  body?: unknown;
  /**
   * 화면을 떠나거나 새 요청으로 바뀌면 이전 요청을 취소한다. 취소되면 abort(reason)의 이유와 상관없이 AbortError를 던진다.
   * AbortSignal.timeout()으로 시간이 지나 끊기면 code가 TIMEOUT인 ApiError를 던진다.
   */
  signal?: AbortSignal;
  /**
   * 이 요청만 모의 응답을 쓰거나(시나리오) 끈다(null). 생략하면 NEXT_PUBLIC_API_MOCK을 따른다.
   * 운영 빌드에서도 적용되므로 /debug 같은 확인 화면에서만 쓴다.
   */
  mock?: MockScenario | null;
}

// 세션 쿠키 인증이라 상태를 바꾸는 요청에는 CSRF 토큰이 필요하다.
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined) params.set(key, String(value));
  }
  const search = params.toString();
  return `${BASE_URL}${path}${search ? `?${search}` : ""}`;
}

/** fetch가 아닌 곳(EventSource 등)에서 쓸 API 주소. path는 /api 뒤의 경로다 */
export function apiUrl(path: string) {
  return buildUrl(path.startsWith("/") ? path : `/${path}`);
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== "object" || value === null) return false;
  const { code, message, details } = value as Record<string, unknown>;
  // 프록시가 임의 JSON을 돌려줘도 details를 배열로 다룰 수 있을 때만 공통 형식으로 본다.
  return (
    typeof code === "string" &&
    typeof message === "string" &&
    (details === undefined || Array.isArray(details))
  );
}

/** 요청이나 본문 읽기가 실패했을 때 던질 값. 시간 초과는 TIMEOUT, 그 밖의 취소는 표준 AbortError로 바꾼다. */
function toFailure(e: unknown, signal?: AbortSignal): unknown {
  if (signal?.aborted) {
    const reason: unknown = signal.reason;
    if (reason instanceof DOMException && reason.name === "TimeoutError") {
      return new ApiError(
        0,
        TIMEOUT,
        "서버 응답이 늦어 요청을 멈췄습니다. 잠시 후 다시 시도해 주세요.",
      );
    }
    // abort(reason)에 이유를 넣으면 그 값이 그대로 던져져, isAbortError가 알아보도록 표준 AbortError로 바꾼다.
    return isAbortError(e) ? e : new DOMException("요청을 취소했습니다.", "AbortError");
  }
  return new ApiError(0, NETWORK_ERROR, "서버에 연결하지 못했습니다. 네트워크를 확인해 주세요.");
}

// 본문은 응답 헤더보다 늦게 오므로 읽는 중에도 취소·연결 끊김이 날 수 있다.
async function readText(response: Response, signal?: AbortSignal) {
  try {
    return await response.text();
  } catch (e) {
    throw toFailure(e, signal);
  }
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

async function toApiError(response: Response, signal?: AbortSignal): Promise<ApiError> {
  const retryAfter = Number(response.headers.get("Retry-After"));
  const retryAfterSeconds = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null;
  const body = parseJson(await readText(response, signal));
  if (isErrorBody(body)) {
    return new ApiError(
      response.status,
      body.code,
      body.message,
      body.details ?? [],
      retryAfterSeconds,
    );
  }
  return new ApiError(
    response.status,
    UNEXPECTED_RESPONSE,
    "서버 응답을 처리하지 못했습니다.",
    [],
    retryAfterSeconds,
  );
}

/**
 * BE API를 호출한다. 성공하면 본문을 그대로(본문이 없으면 undefined), 실패하면 ApiError를 던진다.
 * path는 /api 뒤의 경로다. 예: request("POST", "/v1/users/signup", { body })
 */
export function request<T>(method: string, path: string, options: RequestOptions = {}) {
  return send<T>(method, path, options, false);
}

async function send<T>(
  method: string,
  path: string,
  options: RequestOptions,
  csrfRetried: boolean,
): Promise<T> {
  const { query, body, signal, mock = DEFAULT_MOCK } = options;
  // 브라우저는 PATCH를 대문자로 바꿔 주지 않아, 소문자로 넘기면 서버가 405로 막는다.
  const verb = method.toUpperCase();
  const route = path.startsWith("/") ? path : `/${path}`;
  const headers = new Headers({ Accept: "application/json" });
  let payload: BodyInit | undefined;
  if (body instanceof FormData || body instanceof Blob || body instanceof URLSearchParams) {
    // Content-Type은 브라우저가 본문 종류에 맞춰 넣는다 (multipart는 boundary 포함).
    payload = body;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }
  if (csrfToken && UNSAFE_METHODS.has(verb)) headers.set("X-CSRF-TOKEN", csrfToken);

  let response: Response;
  try {
    response = mock
      ? await mockFetch(mock, verb, route, signal)
      : await fetch(buildUrl(route, query), {
          method: verb,
          headers,
          body: payload,
          signal,
          credentials: "same-origin",
        });
  } catch (e) {
    throw toFailure(e, signal);
  }

  if (!response.ok) {
    const error = await toApiError(response, signal);
    // 토큰이 없거나 바뀌었으면 내 계정 조회로 다시 받아 한 번만 다시 보낸다. 조회가 401이면 UNAUTHORIZED를 던진다.
    if (error.code === "CSRF_INVALID" && UNSAFE_METHODS.has(verb) && !csrfRetried) {
      const me = await send<LoginResponse>("GET", "/v1/users/me", { signal, mock }, true);
      setCsrfToken(me.csrfToken);
      return send<T>(method, path, options, true);
    }
    throw error;
  }
  // 204나 본문 없는 200은 undefined. 프록시가 index.html을 200으로 돌려주는 경우 등은 ApiError로 바꾼다.
  const text = await readText(response, signal);
  if (text === "") return undefined as T;
  const data = parseJson(text);
  if (data === undefined) {
    throw new ApiError(response.status, UNEXPECTED_RESPONSE, "서버 응답을 처리하지 못했습니다.");
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>("GET", path, options),
  post: <T>(path: string, options?: RequestOptions) => request<T>("POST", path, options),
  put: <T>(path: string, options?: RequestOptions) => request<T>("PUT", path, options),
  patch: <T>(path: string, options?: RequestOptions) => request<T>("PATCH", path, options),
  delete: <T = void>(path: string, options?: RequestOptions) => request<T>("DELETE", path, options),
};

/** 요청 취소로 끝난 경우. 화면에 오류로 보여 주지 않을 때 쓴다. */
export function isAbortError(e: unknown) {
  return e instanceof DOMException && e.name === "AbortError";
}
