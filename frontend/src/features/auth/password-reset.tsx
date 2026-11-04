"use client";

import { useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { FieldError } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { TextField } from "@/components/ui/text-field";
import { api, ApiError, failText, type CodeSent, type PasswordResetVerified } from "@/lib/api";
import { useRequest } from "@/lib/hooks/use-request";
import { isValidEmail, passwordRule } from "@/lib/validation";

import { CodeField, useVerificationCode } from "./code-field";

export type ResetStep = "email" | "code" | "pw";

const SUBTITLE: Record<ResetStep, (email: string) => string> = {
  email: () => "가입한 이메일을 입력하면 인증 코드를 보내 드려요.",
  code: (email) =>
    `${email}(으)로 6자리 인증 코드를 보냈어요. 메일이 안 보이면 스팸함도 확인해 주세요.`,
  pw: () => "새로 쓸 비밀번호를 입력해 주세요.",
};
const STEP_NO: Record<ResetStep, number> = { email: 1, code: 2, pw: 3 };

/** 비밀번호 재설정 3단계 (USERS-005, API-USERS-008~010). 이메일 → 인증 코드 → 새 비밀번호 */
export function PasswordReset({
  initialEmail,
  onBack,
  onDone,
}: {
  initialEmail: string;
  /** 1단계에서 뒤로: 로그인 화면으로 */
  onBack: () => void;
  /** 변경 완료. 로그인 화면에 완료 안내 + 이메일 채움 */
  onDone: (email: string) => void;
}) {
  const [step, setStep] = useState<ResetStep>("email");
  const [email, setEmail] = useState(initialEmail);
  const code = useVerificationCode();
  const [resetToken, setResetToken] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { pending, run: request, cancel } = useRequest<"send" | "verify" | "save">();
  const busy = pending !== null;
  /** 서버 상태를 바꾸는 요청(코드 확인·비밀번호 저장) 중에는 끊으면 화면과 서버가 어긋나므로 이전을 막는다 */
  const locked = pending === "verify" || pending === "save";

  const emailOk = isValidEmail(email);
  const pwRule = passwordRule(pw);
  const pwOk = pwRule.ok;

  /** 단계마다 입력 대상이 하나라 실패 문구는 지금 단계의 입력 아래 한 곳에 보여 준다 */
  const run = (
    kind: "send" | "verify" | "save",
    req: (signal: AbortSignal) => Promise<void>,
    fail: (e: unknown) => void = (e) => setErr(failText(e)),
  ) => {
    setErr(null);
    return request(kind, req, fail);
  };

  const send = () =>
    run(
      "send",
      async (signal) => {
        const sent = await api.post<CodeSent>("/v1/users/password-reset", {
          body: { email },
          signal,
        });
        code.sent(sent);
        setStep("code");
      },
      (e) => {
        setErr(failText(e));
        code.blockResend(e);
      },
    );

  const verify = () =>
    run("verify", async (signal) => {
      const verified = await api.post<PasswordResetVerified>(
        "/v1/users/password-reset/verification",
        { body: { email, code: code.code }, signal },
      );
      setResetToken(verified.resetToken);
      setPw("");
      setPw2("");
      setStep("pw");
    });

  const save = () =>
    run(
      "save",
      async (signal) => {
        await api.put("/v1/users/password-reset/password", {
          body: { resetToken, newPassword: pw, newPasswordConfirm: pw2 },
          signal,
        });
        onDone(email.trim());
      },
      (e) => {
        setErr(failText(e));
        // 재설정 시간이 지났으면 인증 코드부터 다시 받는다
        if (e instanceof ApiError && e.code === "USERS_RESET_TOKEN_EXPIRED") {
          code.clear();
          setStep("code");
        }
      },
    );

  const back = () => {
    if (locked) return;
    cancel();
    setErr(null);
    // 확인에 쓴 인증 코드는 서버에서 지워져 다시 쓸 수 없다. 남은 시간을 지워 다시 받게 한다
    if (step === "pw") {
      code.clear();
      setStep("code");
    } else if (step === "code") setStep("email");
    else onBack();
  };

  return (
    <>
      <div className="flex flex-col gap-2.5">
        <span className="font-serif text-[30px] leading-none text-navy italic">mairor</span>
        <div className="flex items-baseline gap-3.5">
          <h1 className="font-display text-[40px] leading-[1.25] text-ink">비밀번호 재설정</h1>
          <span className="font-label text-[15px] font-semibold tracking-[.12em] text-navy tabular">
            {STEP_NO[step]} / 3
          </span>
        </div>
        <p className="text-[17px] leading-[1.5] text-mute">{SUBTITLE[step](email.trim())}</p>
      </div>

      <div className="flex flex-col gap-3">
        {step === "email" && (
          <>
            <TextField
              type="email"
              placeholder="가입한 이메일"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setErr(null);
                // 다시 받기 대기는 이메일마다 따로다
                code.resetResend();
              }}
              autoComplete="email"
              maxLength={254}
            />
            {err && <FieldError>{err}</FieldError>}
            <span className="text-[15px] leading-[1.5] text-mute">
              Google로 가입했다면 비밀번호 없이 &apos;Google로 계속하기&apos;로 로그인해 주세요.
            </span>
            <div className="mt-1 flex gap-3">
              <IconButton onClick={back} disabled={locked} title="이전" aria-label="이전" />
              <PillButton
                className="flex-1"
                busy={busy}
                disabled={!emailOk || code.resendLeft > 0}
                onClick={send}
              >
                {busy
                  ? "보내는 중"
                  : code.resendLeft > 0
                    ? `${code.resendLeft}초 후 다시 받기`
                    : "인증 코드 받기"}
              </PillButton>
            </div>
          </>
        )}

        {step === "code" && (
          <>
            <CodeField
              code={code}
              noun="인증 코드"
              error={err}
              busy={busy}
              inputClassName="text-[22px] font-semibold tracking-[.3em]"
              onInput={() => setErr(null)}
              onResend={send}
              onSubmit={verify}
            />
            <div className="mt-1 flex gap-3">
              <IconButton onClick={back} disabled={locked} title="이전" aria-label="이전" />
              <PillButton
                className="flex-1"
                busy={pending === "verify"}
                disabled={!code.ready || busy}
                onClick={verify}
              >
                {pending === "verify" ? "확인 중" : "확인"}
              </PillButton>
            </div>
          </>
        )}

        {step === "pw" && (
          <>
            <TextField
              type="password"
              placeholder="새 비밀번호"
              value={pw}
              onChange={(e) => {
                setPw(e.target.value);
                setErr(null);
              }}
              autoComplete="new-password"
            />
            <span
              className={`text-[15px] ${!pw ? "text-mute" : pwOk ? "text-mint-ink" : "text-error"}`}
            >
              8~64자 · 영문·숫자·특수문자 포함 · 72바이트 이하
            </span>
            {!pwRule.bytes && (
              <FieldError>72바이트를 넘었어요. 한글 등은 글자당 3바이트로 계산돼요.</FieldError>
            )}
            <TextField
              type="password"
              placeholder="새 비밀번호 확인"
              value={pw2}
              onChange={(e) => {
                setPw2(e.target.value);
                setErr(null);
              }}
              autoComplete="new-password"
            />
            {!!pw2 && pw !== pw2 && <FieldError>비밀번호가 서로 달라요.</FieldError>}
            {err && <FieldError>{err}</FieldError>}
            <div className="mt-1 flex gap-3">
              <IconButton onClick={back} disabled={locked} title="이전" aria-label="이전" />
              <PillButton
                className="flex-1"
                busy={busy}
                disabled={!pwOk || pw !== pw2}
                onClick={save}
              >
                {busy ? "바꾸는 중" : "비밀번호 바꾸기"}
              </PillButton>
            </div>
          </>
        )}
      </div>
    </>
  );
}
