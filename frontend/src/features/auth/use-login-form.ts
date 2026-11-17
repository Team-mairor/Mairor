"use client";

import { useState } from "react";

import { useSessionActions } from "@/domain/session";
import {
  api,
  ApiError,
  errorMessage,
  type LoginRequest,
  type LoginResponse,
  type User,
} from "@/lib/api";
import { useCountdown } from "@/lib/hooks/use-countdown";
import { useRequest } from "@/lib/hooks/use-request";
import { normalizeEmail } from "@/lib/validation";

/**
 * 이메일 로그인 입력과 제출. 반복해서 틀리면 서버가 잠그고(429), 그동안은 Retry-After 초만큼
 * 버튼을 막는다
 */
export function useLoginForm({
  onSuccess,
}: {
  onSuccess: (user: Pick<User, "email" | "nickname">, csrfToken?: string) => void;
}) {
  const { sessionChecked } = useSessionActions();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  /** 로그인 실패 안내. 서버가 준 문구 */
  const [error, setError] = useState<string | null>(null);
  /** 서버 잠금은 이메일마다라, 잠긴 이메일과 풀리는 시각을 함께 둔다 */
  const [lock, setLock] = useState<{ email: string; until: number } | null>(null);
  /** 서버 혼잡(TOO_MANY_REQUESTS)이 풀리는 시각. 이메일과 상관없이 서버 전체에 걸린다 */
  const [crowdUntil, setCrowdUntil] = useState<number | null>(null);
  const { pending, run } = useRequest<"login">();
  const busy = pending !== null;

  // 다른 이메일로 바꾸면 그 이메일은 잠기지 않았으니 바로 시도할 수 있다
  const lockLeft = useCountdown(lock?.email === normalizeEmail(email) ? lock.until : null);
  const crowdLeft = useCountdown(crowdUntil);
  const waitLeft = Math.max(lockLeft, crowdLeft);
  // 첫 내 계정 조회가 끝나기 전에 로그인하면 늦게 온 401이 로그인 결과를 덮고, 온보딩 기록도 아직 못 읽었다
  const canLogin = sessionChecked && !!email.trim() && !!pw && !busy && waitLeft === 0;

  const submit = () => {
    if (!canLogin) return;
    setError(null);
    return run(
      "login",
      async (signal) => {
        const { user, csrfToken } = await api.post<LoginResponse>("/v1/users/login", {
          body: { email, password: pw } satisfies LoginRequest,
          signal,
        });
        onSuccess(user, csrfToken);
      },
      (e) => {
        if (!(e instanceof ApiError)) return setError(errorMessage(e));
        // 잠금 안내는 이메일 잠금(USERS_LOGIN_RATE_LIMITED)만. 서버 혼잡(TOO_MANY_REQUESTS)은 시도 횟수와 무관하다
        if (e.code === "USERS_LOGIN_RATE_LIMITED" && e.retryAfterSeconds) {
          return setLock({
            email: normalizeEmail(email),
            until: Date.now() + e.retryAfterSeconds * 1000,
          });
        }
        if (e.code === "TOO_MANY_REQUESTS" && e.retryAfterSeconds) {
          setCrowdUntil(Date.now() + e.retryAfterSeconds * 1000);
        }
        setError(
          e.code === "TOO_MANY_REQUESTS"
            ? "요청이 몰려 처리하지 못했어요. 잠시 후 다시 시도해 주세요."
            : errorMessage(e),
        );
      },
    );
  };

  return {
    email,
    pw,
    error,
    busy,
    sessionChecked,
    lockLeft,
    waitLeft,
    canLogin,
    submit,
    changeEmail: (value: string) => {
      setEmail(value);
      setError(null);
    },
    changePw: (value: string) => {
      setPw(value);
      setError(null);
    },
    /** 주소로 받은 이메일을 입력 칸에 채운다 */
    prefillEmail: setEmail,
    clearError: () => setError(null),
    /** 비밀번호를 바꾸고 돌아오면 그 이메일로 새 비밀번호를 입력하게 한다 */
    finishReset: (who: string) => {
      setEmail(who);
      setPw("");
      setError(null);
    },
    clearPassword: () => {
      setPw("");
      setError(null);
    },
  };
}

export type LoginForm = ReturnType<typeof useLoginForm>;
