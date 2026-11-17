"use client";

import { useState } from "react";

import {
  api,
  ApiError,
  failText,
  type CodeSent,
  type EmailAvailability,
  type EmailVerified,
} from "@/lib/api";
import { useCountdown } from "@/lib/hooks/use-countdown";
import { isValidEmail, normalizeEmail } from "@/lib/validation";

import { useVerificationCode } from "./code-field";

export type EmailError = { kind: "dup" } | { kind: "msg"; text: string } | null;

type Run = (
  kind: "check" | "send" | "verify",
  req: (signal: AbortSignal) => Promise<void>,
  fail: (e: unknown) => void,
) => Promise<void>;

/**
 * 회원가입의 이메일 입력·중복 확인·인증번호. 확인한 주소(okFor)와 인증번호를 보낸 주소(sentFor)가
 * 지금 입력과 같을 때만 확인·발송·인증을 마친 것으로 본다
 */
export function useSignupEmail({
  pending,
  run,
}: {
  /** 지금 진행 중인 요청. 진행 중에는 새 요청을 막는다 */
  pending: string | null;
  run: Run;
}) {
  const [email, setEmail] = useState("");
  const [okFor, setOkFor] = useState("");
  const [sentFor, setSentFor] = useState("");
  const [verified, setVerified] = useState<{ email: string; token: string } | null>(null);
  const [error, setError] = useState<EmailError>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [checkUntil, setCheckUntil] = useState<number | null>(null);
  const checkLeft = useCountdown(checkUntil);
  const code = useVerificationCode();

  const normalized = normalizeEmail(email);
  const valid = isValidEmail(email);
  const checked = valid && okFor === normalized;
  const sent = checked && sentFor === normalized;
  const verifiedNow = checked && verified?.email === normalized;
  const canCheck = valid && !checked && !pending && checkLeft === 0;
  const canVerify = code.ready && !pending;

  const change = (value: string) => {
    setEmail(value);
    setError(null);
    setCodeError(null);
    code.resetResend();
  };

  /** 인증을 마친 주소를 바꾸려고 처음 상태로 되돌린다 */
  const reset = () => {
    setOkFor("");
    setSentFor("");
    setVerified(null);
    code.clear();
  };

  const markDuplicate = () => {
    setOkFor("");
    setError({ kind: "dup" });
  };

  /** 서버가 인증이 안 됐다고 하면 인증번호부터 다시 받게 한다 */
  const markNotVerified = (message: string) => {
    setSentFor("");
    setVerified(null);
    setError({ kind: "msg", text: message });
  };

  const check = () => {
    if (!canCheck) return;
    setError(null);
    return run(
      "check",
      async (signal) => {
        const { available } = await api.post<EmailAvailability>("/v1/users/email-availability", {
          body: { email: normalized },
          signal,
        });
        if (available) setOkFor(normalized);
        else markDuplicate();
      },
      (e) => {
        setError({ kind: "msg", text: failText(e) });
        if (e instanceof ApiError && e.retryAfterSeconds) {
          setCheckUntil(Date.now() + e.retryAfterSeconds * 1000);
        }
      },
    );
  };

  const sendCode = () => {
    setCodeError(null);
    return run(
      "send",
      async (signal) => {
        const res = await api.post<CodeSent>("/v1/users/email-verification", {
          body: { email: normalized },
          signal,
        });
        setSentFor(normalized);
        setVerified(null);
        code.sent(res);
      },
      (e) => {
        if (e instanceof ApiError && e.code === "USERS_EMAIL_DUPLICATE") return markDuplicate();
        setCodeError(failText(e));
        code.blockResend(e);
      },
    );
  };

  const verify = () => {
    setCodeError(null);
    return run(
      "verify",
      async (signal) => {
        const res = await api.post<EmailVerified>("/v1/users/email-verification/verification", {
          body: { email: normalized, code: code.code },
          signal,
        });
        setVerified({ email: normalized, token: res.verificationToken });
      },
      (e) => setCodeError(failText(e)),
    );
  };

  return {
    email,
    normalized,
    valid,
    checked,
    sent,
    verified: verifiedNow,
    token: verified?.token,
    error,
    setError,
    clearError: () => setError(null),
    codeError,
    clearCodeError: () => setCodeError(null),
    code,
    checkLeft,
    canCheck,
    canVerify,
    change,
    reset,
    markDuplicate,
    markNotVerified,
    check,
    sendCode,
    verify,
  };
}

export type SignupEmail = ReturnType<typeof useSignupEmail>;
