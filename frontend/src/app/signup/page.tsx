"use client";

import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { FieldError, Notice } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { Spinner } from "@/components/ui/spinner";
import { TextField } from "@/components/ui/text-field";
import {
  AgreementFields,
  CodeField,
  EXTRA_FIELDS,
  ProfileFields,
  useProfileForm,
  useVerificationCode,
} from "@/features/auth";
import {
  api,
  ApiError,
  errorMessage,
  failText,
  type CodeSent,
  type EmailAvailability,
  type EmailVerified,
  type SignUpRequest,
  type User,
} from "@/lib/api";
import { useCountdown } from "@/lib/hooks/use-countdown";
import { useRequest } from "@/lib/hooks/use-request";
import { cn } from "@/lib/utils";
import { isValidEmail, normalizeEmail, passwordRule } from "@/lib/validation";

/**
 * 가입 전에 이메일 인증을 거칠지. BE의 SIGNUP_REQUIRE_EMAIL_VERIFICATION과 맞춘다.
 * 메일 발송이 꺼진(MAIL_ENABLED=false) 환경에서는 "false"로 빌드해야 가입할 수 있다.
 */
const EMAIL_VERIFICATION = process.env.NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION !== "false";

/** dup: 이미 가입된 이메일, msg: 서버가 준 안내 문구 */
type EmailError = { kind: "dup" } | { kind: "msg"; text: string } | null;

/** 진행 중인 요청: 중복 확인, 인증번호 받기, 인증번호 확인, 가입 */
type Pending = "check" | "send" | "verify" | "submit";

function RuleItem({ ok, children }: { ok: boolean; children: string }) {
  return (
    <span className={cn("flex items-center gap-1.5", ok ? "text-navy" : "text-ash-2")}>
      <Check className="size-3.5" strokeWidth={3} aria-hidden />
      {children}
    </span>
  );
}

/** 이메일 칸 옆 버튼. done: 끝난 단계(초록), on: 누를 수 있음 */
function SideButton({
  tone,
  busy,
  children,
  ...props
}: React.ComponentProps<"button"> & { tone: "done" | "on" | "off"; busy?: boolean }) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        "flex h-[60px] shrink-0 items-center justify-center gap-2 rounded-2xl border px-5 text-[17px] font-semibold whitespace-nowrap",
        tone === "done"
          ? "border-mint bg-mint-pale text-mint-ink"
          : tone === "on"
            ? "border-navy bg-white text-navy"
            : "border-line-2 bg-white text-ash-2",
      )}
    >
      {busy && <Spinner tone="brand" className="size-4 border-blush border-t-navy" />}
      {children}
    </button>
  );
}

/** 입력 칸에서 Enter를 가입 제출 대신 그 칸의 동작으로 보낸다. 한글 조합 중 Enter는 무시한다 */
const onEnter = (action: () => void) => (e: React.KeyboardEvent<HTMLInputElement>) => {
  if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
  e.preventDefault();
  action();
};

/** 01-1 회원가입. 이메일 중복 확인 → 이메일 인증(EMAIL_VERIFICATION) → 비밀번호 규칙 → 약관 동의 → 가입 */
export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const form = useProfileForm();
  /** 가입할 수 있다고 확인한 이메일 */
  const [okFor, setOkFor] = useState("");
  /** 인증번호를 보낸 이메일 */
  const [sentFor, setSentFor] = useState("");
  const code = useVerificationCode();
  /** 인증을 마친 이메일과 가입 요청에 실을 토큰 */
  const [verified, setVerified] = useState<{ email: string; token: string } | null>(null);
  const [emailErr, setEmailErr] = useState<EmailError>(null);
  const [codeErr, setCodeErr] = useState<string | null>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);
  const [pw2Err, setPw2Err] = useState<string | null>(null);
  const [formErr, setFormErr] = useState<string | null>(null);
  const { pending, run } = useRequest<Pending>();
  /** 중복 확인 요청 제한(429)이 풀리는 시각 */
  const [checkUntil, setCheckUntil] = useState<number | null>(null);
  const checkLeft = useCountdown(checkUntil);

  const emN = normalizeEmail(email);
  const emailOk = isValidEmail(email);
  const rule = passwordRule(pw);
  const match = pw2.length > 0 && pw === pw2;
  // 이메일을 바꾸면 중복 확인·인증을 다시 해야 한다. 빈 칸끼리 같다고 확인·발송된 것으로 보지 않는다
  const checked = emailOk && okFor === emN;
  const sent = checked && sentFor === emN;
  const done = checked && verified?.email === emN;
  const canCheck = emailOk && !checked && !pending && checkLeft === 0;
  const canVerify = code.ready && !pending;
  const emailReady = EMAIL_VERIFICATION ? done : checked;
  const canSubmit = emailOk && emailReady && rule.ok && match && form.ready && !pending;

  /** 인증을 마친 이메일을 풀어 다시 입력하게 한다 */
  const changeEmail = () => {
    setOkFor("");
    setSentFor("");
    setVerified(null);
    code.clear();
  };

  const dup = () => {
    setOkFor("");
    setEmailErr({ kind: "dup" });
  };

  /** 이메일 중복 확인 */
  const checkEmail = () => {
    if (!canCheck) return;
    setEmailErr(null);
    return run(
      "check",
      async (signal) => {
        const { available } = await api.post<EmailAvailability>("/v1/users/email-availability", {
          body: { email: emN },
          signal,
        });
        if (available) setOkFor(emN);
        else dup();
      },
      (e) => {
        setEmailErr({ kind: "msg", text: failText(e) });
        if (e instanceof ApiError && e.retryAfterSeconds) {
          setCheckUntil(Date.now() + e.retryAfterSeconds * 1000);
        }
      },
    );
  };

  /** 인증번호 받기. 이미 가입된 이메일이면 409 */
  const sendCode = () => {
    setCodeErr(null);
    return run(
      "send",
      async (signal) => {
        const res = await api.post<CodeSent>("/v1/users/email-verification", {
          body: { email: emN },
          signal,
        });
        setSentFor(emN);
        setVerified(null);
        code.sent(res);
      },
      (e) => {
        if (e instanceof ApiError && e.code === "USERS_EMAIL_DUPLICATE") return dup();
        setCodeErr(failText(e));
        code.blockResend(e);
      },
    );
  };

  /** 인증번호 확인 */
  const verifyCode = () => {
    setCodeErr(null);
    return run(
      "verify",
      async (signal) => {
        const res = await api.post<EmailVerified>("/v1/users/email-verification/verification", {
          body: { email: emN, code: code.code },
          signal,
        });
        setVerified({ email: emN, token: res.verificationToken });
      },
      (e) => setCodeErr(failText(e)),
    );
  };

  const onSubmitError = (e: unknown) => {
    if (!(e instanceof ApiError)) return setFormErr(errorMessage(e));
    if (e.code === "USERS_EMAIL_DUPLICATE") return dup();
    if (e.code === "USERS_EMAIL_NOT_VERIFIED") {
      // 인증 토큰이 만료됐다. 인증번호부터 다시 받는다
      setSentFor("");
      setVerified(null);
      return setEmailErr({ kind: "msg", text: e.message });
    }
    if (form.applyError(e)) return;
    if (e.code !== "VALIDATION_FAILED") return setFormErr(errorMessage(e));
    const reason = (field: string) => e.details.find((d) => d.field === field)?.reason ?? null;
    const emailReason = reason("email");
    if (emailReason) setEmailErr({ kind: "msg", text: emailReason });
    setPwErr(reason("password"));
    setPw2Err(reason("passwordConfirm"));
    // 짝이 되는 칸이 없는 오류(본문·약관 항목 등)는 폼 아래에 보여 준다
    const known: string[] = ["email", "password", "passwordConfirm", ...EXTRA_FIELDS];
    if (e.details.some((d) => !known.includes(d.field))) setFormErr(e.message);
  };

  /** 회원가입 */
  const submit = () => {
    if (!canSubmit) return;
    setEmailErr(null);
    setPwErr(null);
    setPw2Err(null);
    setFormErr(null);
    form.clearErrors();
    return run(
      "submit",
      async (signal) => {
        await api.post<User>("/v1/users/signup", {
          body: {
            email: emN,
            password: pw,
            passwordConfirm: pw2,
            ...form.payload(),
            emailVerificationToken: verified?.token,
          } satisfies SignUpRequest,
          signal,
        });
        router.replace(`/login?signup=done&email=${encodeURIComponent(emN)}`);
      },
      onSubmitError,
    );
  };

  const emailBad = email.length > 3 && !emailOk;

  return (
    <main className="flex flex-1 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton
          size={44}
          onClick={() => router.push("/login")}
          title="로그인으로"
          aria-label="로그인으로"
        />
        <span className="font-serif text-[28px] leading-none text-navy italic">Sign up</span>
        <span className="text-[17px] text-mute">회원가입</span>
      </header>

      <form
        className="flex min-h-0 flex-1 flex-col gap-10 overflow-y-auto px-10 pt-12 pb-8"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex flex-col gap-2.5">
          <h1 className="font-display text-[38px] leading-[1.3] text-ink">
            이메일로 mairor를
            <br />
            시작해 볼까요?
          </h1>
          <p className="text-[17px] leading-[1.5] text-mute">
            파우치와 메이크업 리포트가 이 계정에 저장돼요.
          </p>
        </div>

        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <label htmlFor="su-email" className="text-[16px] font-bold text-ink">
              이메일
            </label>
            <div className="flex gap-2.5">
              <TextField
                id="su-email"
                type="email"
                placeholder="name@example.com"
                value={email}
                invalid={emailBad || !!emailErr}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setEmailErr(null);
                  setCodeErr(null);
                  // 인증번호 다시 받기 대기는 이메일마다 따로다
                  code.resetResend();
                }}
                // Enter는 가입이 아니라 이 칸의 다음 동작(중복 확인)으로 보낸다
                onKeyDown={onEnter(checkEmail)}
                autoComplete="email"
                maxLength={254}
                // 인증을 마치면 잠근다. 바꾸려면 '이메일 변경'으로 풀고 다시 인증한다
                readOnly={done}
                className={cn("flex-1", done && "bg-cream text-mute")}
              />
              <SideButton
                tone={done ? "on" : checked ? "done" : canCheck ? "on" : "off"}
                busy={pending === "check"}
                onClick={done ? changeEmail : checkEmail}
                disabled={done ? !!pending : !canCheck}
              >
                {done
                  ? "이메일 변경"
                  : pending === "check"
                    ? "확인 중"
                    : checked
                      ? "확인 완료"
                      : checkLeft > 0
                        ? `${checkLeft}초 후`
                        : "중복 확인"}
              </SideButton>
            </div>
            {emailBad && <FieldError>이메일 형식을 확인해 주세요.</FieldError>}
            {checked && !emailErr && (
              <span className="flex items-center gap-1.5 text-[15px] text-mint-ink">
                <Check className="size-3.5" strokeWidth={3} aria-hidden />
                {done ? "이메일 인증을 마쳤어요." : "사용할 수 있는 이메일이에요."}
              </span>
            )}
            {emailOk && !checked && !emailErr && rule.ok && match && (
              <span className="text-[15px] text-mute">이메일 중복 확인을 해 주세요.</span>
            )}
            {emailErr?.kind === "dup" && (
              <span
                className="flex flex-wrap items-center gap-2.5 text-[15px] text-error-2"
                role="alert"
              >
                <span>이미 가입된 이메일이에요.</span>
                <button
                  type="button"
                  className="font-bold text-navy underline"
                  onClick={() => router.push(`/login?mode=email&email=${encodeURIComponent(emN)}`)}
                >
                  로그인하기
                </button>
              </span>
            )}
            {emailErr?.kind === "msg" && <FieldError>{emailErr.text}</FieldError>}
          </div>

          {EMAIL_VERIFICATION && checked && !done && (
            <div className="flex flex-col gap-2">
              <label htmlFor="su-code" className="text-[16px] font-bold text-ink">
                이메일 인증
              </label>
              {sent ? (
                <>
                  <CodeField
                    code={code}
                    id="su-code"
                    noun="인증번호"
                    hint="메일로 받은 인증번호를 입력해 주세요"
                    error={codeErr}
                    busy={!!pending}
                    inputClassName="tracking-[.2em]"
                    onInput={() => setCodeErr(null)}
                    onResend={sendCode}
                    onSubmit={verifyCode}
                    side={
                      <SideButton
                        tone={canVerify ? "on" : "off"}
                        busy={pending === "verify"}
                        onClick={verifyCode}
                        disabled={!canVerify}
                      >
                        {pending === "verify" ? "확인 중" : "확인"}
                      </SideButton>
                    }
                  />
                </>
              ) : (
                <>
                  <PillButton
                    variant="outline"
                    busy={pending === "send"}
                    disabled={!!pending || code.resendLeft > 0}
                    onClick={sendCode}
                  >
                    {code.resendLeft > 0 ? `${code.resendLeft}초 후 다시 받기` : "인증번호 받기"}
                  </PillButton>
                  {codeErr && <FieldError>{codeErr}</FieldError>}
                </>
              )}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <label htmlFor="su-pw" className="text-[16px] font-bold text-ink">
              비밀번호
            </label>
            <TextField
              id="su-pw"
              type="password"
              placeholder="8~64자, 영문·숫자·특수문자 포함"
              value={pw}
              invalid={!!pwErr}
              maxLength={64}
              onChange={(e) => {
                setPw(e.target.value);
                setPwErr(null);
              }}
              autoComplete="new-password"
            />
            <div className="flex flex-wrap gap-4 text-[15px]">
              <RuleItem ok={rule.len}>8~64자</RuleItem>
              <RuleItem ok={rule.mix}>영문 · 숫자 포함</RuleItem>
              <RuleItem ok={rule.spec}>특수문자 포함</RuleItem>
              <RuleItem ok={rule.bytes}>72바이트 이하 (한글 1자 3바이트)</RuleItem>
            </div>
            {pwErr && <FieldError>{pwErr}</FieldError>}
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="su-pw2" className="text-[16px] font-bold text-ink">
              비밀번호 확인
            </label>
            <TextField
              id="su-pw2"
              type="password"
              placeholder="비밀번호를 한 번 더 입력해 주세요"
              value={pw2}
              invalid={(pw2.length > 0 && !match) || !!pw2Err}
              maxLength={64}
              onChange={(e) => {
                setPw2(e.target.value);
                setPw2Err(null);
              }}
              autoComplete="new-password"
            />
            {pw2.length > 0 && !match && <FieldError>비밀번호가 일치하지 않아요.</FieldError>}
            {match && pw2Err && <FieldError>{pw2Err}</FieldError>}
          </div>
        </div>

        <ProfileFields form={form} idPrefix="su" />
        <AgreementFields form={form} />

        <div className="mt-auto flex shrink-0 flex-col gap-3 pt-2">
          {formErr && <Notice tone="error">{formErr}</Notice>}
          <PillButton
            type="submit"
            size="xl"
            className="w-full"
            busy={pending === "submit"}
            disabled={!canSubmit}
          >
            {pending === "submit" ? "가입 중" : "가입하기"}
          </PillButton>
        </div>
      </form>
    </main>
  );
}
