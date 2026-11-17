"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Notice } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { api, ApiError, errorMessage, type SignUpRequest, type User } from "@/lib/api";
import { useRequest } from "@/lib/hooks/use-request";

import { AgreementFields, EXTRA_FIELDS, ProfileFields, useProfileForm } from "./profile-form";
import { SignupEmailSection } from "./signup-email-section";
import { SignupPasswordSection } from "./signup-password-section";
import { useSignupEmail } from "./use-signup-email";
import { useSignupPassword } from "./use-signup-password";

const EMAIL_VERIFICATION = process.env.NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION === "true";

type Pending = "check" | "send" | "verify" | "submit";

/** 이메일 회원가입. 이메일 확인·비밀번호·프로필·동의를 모아 한 번에 가입한다 */
export function SignupView() {
  const router = useRouter();
  const { pending, run } = useRequest<Pending>();
  const em = useSignupEmail({ pending, run });
  const password = useSignupPassword();
  const form = useProfileForm();
  const [formError, setFormError] = useState<string | null>(null);

  const emailReady = EMAIL_VERIFICATION ? em.verified : em.checked;
  const canSubmit =
    em.valid && emailReady && password.rule.ok && password.match && form.ready && !pending;

  const onSubmitError = (e: unknown) => {
    if (!(e instanceof ApiError)) return setFormError(errorMessage(e));
    if (e.code === "USERS_EMAIL_DUPLICATE") return em.markDuplicate();
    if (e.code === "USERS_EMAIL_NOT_VERIFIED") return em.markNotVerified(e.message);
    if (form.applyError(e)) return;
    if (e.code !== "VALIDATION_FAILED") return setFormError(errorMessage(e));
    const reason = (field: string) => e.details.find((d) => d.field === field)?.reason ?? null;
    const emailReason = reason("email");
    if (emailReason) em.setError({ kind: "msg", text: emailReason });
    password.setErrors(reason("password"), reason("passwordConfirm"));
    const known: string[] = ["email", "password", "passwordConfirm", ...EXTRA_FIELDS];
    if (e.details.some((d) => !known.includes(d.field))) setFormError(e.message);
  };

  const submit = () => {
    if (!canSubmit) return;
    em.clearError();
    password.clearErrors();
    setFormError(null);
    form.clearErrors();
    return run(
      "submit",
      async (signal) => {
        await api.post<User>("/v1/users/signup", {
          body: {
            email: em.normalized,
            password: password.pw,
            passwordConfirm: password.pw2,
            ...form.payload(),
            emailVerificationToken: em.token,
          } satisfies SignUpRequest,
          signal,
        });
        router.replace(`/login?signup=done&email=${encodeURIComponent(em.normalized)}`);
      },
      onSubmitError,
    );
  };

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
          <SignupEmailSection
            em={em}
            pending={pending}
            verification={EMAIL_VERIFICATION}
            passwordReady={password.rule.ok && password.match}
          />
          <SignupPasswordSection password={password} />
        </div>

        <ProfileFields form={form} idPrefix="su" />
        <AgreementFields form={form} />

        <div className="mt-auto flex shrink-0 flex-col gap-3 pt-2">
          {formError && <Notice tone="error">{formError}</Notice>}
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
