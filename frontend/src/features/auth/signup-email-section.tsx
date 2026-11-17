"use client";

import { Check } from "lucide-react";
import { useRouter } from "next/navigation";

import { FieldError } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { TextField } from "@/components/ui/text-field";
import { cn } from "@/lib/utils";

import { CodeField } from "./code-field";
import { onEnter, SideButton } from "./signup-parts";
import type { SignupEmail } from "./use-signup-email";

/** 이메일 입력과 중복 확인, 인증번호 받기·확인 */
export function SignupEmailSection({
  em,
  pending,
  verification,
  passwordReady,
}: {
  em: SignupEmail;
  pending: string | null;
  /** 가입 전 이메일 인증을 거치는 빌드 */
  verification: boolean;
  /** 비밀번호 규칙과 확인 입력을 모두 맞췄다. 이메일 확인만 남았을 때 안내한다 */
  passwordReady: boolean;
}) {
  const router = useRouter();
  const { code, error } = em;
  const badFormat = em.email.length > 3 && !em.valid;

  return (
    <>
      <div className="flex flex-col gap-2">
        <label htmlFor="su-email" className="text-[16px] font-bold text-ink">
          이메일
        </label>
        <div className="flex gap-2.5">
          <TextField
            id="su-email"
            type="email"
            placeholder="name@example.com"
            value={em.email}
            invalid={badFormat || !!error}
            onChange={(e) => em.change(e.target.value)}
            onKeyDown={onEnter(em.check)}
            autoComplete="email"
            maxLength={254}
            readOnly={em.verified}
            className={cn("flex-1", em.verified && "bg-cream text-mute")}
          />
          <SideButton
            tone={em.verified ? "on" : em.checked ? "done" : em.canCheck ? "on" : "off"}
            busy={pending === "check"}
            onClick={em.verified ? em.reset : em.check}
            disabled={em.verified ? !!pending : !em.canCheck}
          >
            {em.verified
              ? "이메일 변경"
              : pending === "check"
                ? "확인 중"
                : em.checked
                  ? "확인 완료"
                  : em.checkLeft > 0
                    ? `${em.checkLeft}초 후`
                    : "중복 확인"}
          </SideButton>
        </div>
        {badFormat && <FieldError>이메일 형식을 확인해 주세요.</FieldError>}
        {em.checked && !error && (
          <span className="flex items-center gap-1.5 text-[15px] text-mint-ink">
            <Check className="size-3.5" strokeWidth={3} aria-hidden />
            {em.verified ? "이메일 인증을 마쳤어요." : "사용할 수 있는 이메일이에요."}
          </span>
        )}
        {em.valid && !em.checked && !error && passwordReady && (
          <span className="text-[15px] text-mute">이메일 중복 확인을 해 주세요.</span>
        )}
        {error?.kind === "dup" && (
          <span
            className="flex flex-wrap items-center gap-2.5 text-[15px] text-error-2"
            role="alert"
          >
            <span>이미 가입된 이메일이에요.</span>
            <button
              type="button"
              className="font-bold text-navy underline"
              onClick={() =>
                router.push(`/login?mode=email&email=${encodeURIComponent(em.normalized)}`)
              }
            >
              로그인하기
            </button>
          </span>
        )}
        {error?.kind === "msg" && <FieldError>{error.text}</FieldError>}
      </div>

      {verification && em.checked && !em.verified && (
        <div className="flex flex-col gap-2">
          <label htmlFor="su-code" className="text-[16px] font-bold text-ink">
            이메일 인증
          </label>
          {em.sent ? (
            <CodeField
              code={code}
              id="su-code"
              noun="인증번호"
              hint="메일로 받은 인증번호를 입력해 주세요"
              error={em.codeError}
              busy={!!pending}
              inputClassName="tracking-[.2em]"
              onInput={em.clearCodeError}
              onResend={em.sendCode}
              onSubmit={em.verify}
              side={
                <SideButton
                  tone={em.canVerify ? "on" : "off"}
                  busy={pending === "verify"}
                  onClick={em.verify}
                  disabled={!em.canVerify}
                >
                  {pending === "verify" ? "확인 중" : "확인"}
                </SideButton>
              }
            />
          ) : (
            <>
              <PillButton
                variant="outline"
                busy={pending === "send"}
                disabled={!!pending || code.resendLeft > 0}
                onClick={em.sendCode}
              >
                {code.resendLeft > 0 ? `${code.resendLeft}초 후 다시 받기` : "인증번호 받기"}
              </PillButton>
              {em.codeError && <FieldError>{em.codeError}</FieldError>}
            </>
          )}
        </div>
      )}
    </>
  );
}
