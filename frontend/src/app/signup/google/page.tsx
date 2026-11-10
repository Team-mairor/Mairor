"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Notice } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { Spinner } from "@/components/ui/spinner";
import { TextField } from "@/components/ui/text-field";
import { AgreementFields, ProfileFields, useProfileForm } from "@/features/auth";
import { useSession } from "@/features/session";
import {
  api,
  ApiError,
  errorMessage,
  isAbortError,
  type GoogleSignUpRequest,
  type GoogleSignupPending,
  type LoginResponse,
} from "@/lib/api";
import { useRequest } from "@/lib/hooks/use-request";
import { profileProblem } from "@/lib/validation";

/** 가입 대기가 끝나 로그인 화면에서 안내할 코드 */
const BACK_TO_LOGIN = new Set(["USERS_GOOGLE_SIGNUP_EXPIRED", "USERS_ACCOUNT_LINK_REQUIRED"]);

const loginWithError = (code: string) => `/login?error=${encodeURIComponent(code)}`;

export default function GoogleSignupPage() {
  const router = useRouter();
  const [pendingSignup, setPendingSignup] = useState<GoogleSignupPending | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    api
      .get<GoogleSignupPending>("/v1/users/oauth/google/signup", { signal: ctrl.signal })
      .then(setPendingSignup)
      .catch((e) => {
        if (isAbortError(e)) return;
        if (e instanceof ApiError && BACK_TO_LOGIN.has(e.code)) {
          return router.replace(loginWithError(e.code));
        }
        setLoadErr(errorMessage(e));
      });
    return () => ctrl.abort();
  }, [router]);

  if (pendingSignup) return <GoogleSignupForm pendingSignup={pendingSignup} />;
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 bg-white px-10">
      {loadErr ? (
        <>
          <Notice tone="error">{loadErr}</Notice>
          <PillButton variant="outline" onClick={() => router.replace("/login")}>
            로그인으로
          </PillButton>
        </>
      ) : (
        <Spinner tone="brand" className="size-8" />
      )}
    </main>
  );
}

function GoogleSignupForm({ pendingSignup }: { pendingSignup: GoogleSignupPending }) {
  const router = useRouter();
  const { state, signIn } = useSession();
  const { pending, run } = useRequest<"submit">();
  const [formErr, setFormErr] = useState<string | null>(null);
  // Google 표시 이름이 이름 규칙에 맞을 때만 채운다
  const googleName = pendingSignup.name ?? "";
  const form = useProfileForm({
    name: googleName && !profileProblem("name", googleName) ? googleName : "",
  });
  const busy = pending === "submit";
  const canSubmit = form.ready && !busy;

  const submit = () => {
    if (!canSubmit) return;
    setFormErr(null);
    form.clearErrors();
    return run(
      "submit",
      async (signal) => {
        const { user, csrfToken } = await api.post<LoginResponse>("/v1/users/oauth/google/signup", {
          body: form.payload() satisfies GoogleSignUpRequest,
          signal,
        });
        signIn(user, csrfToken);
        router.replace(state.onboarded ? "/home" : "/onboarding");
      },
      (e) => {
        if (e instanceof ApiError && BACK_TO_LOGIN.has(e.code)) {
          return router.replace(loginWithError(e.code));
        }
        if (!form.applyError(e)) setFormErr(errorMessage(e));
      },
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
        <span className="text-[17px] text-mute">Google로 가입</span>
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
            Google 계정으로
            <br />
            mairor를 시작해요
          </h1>
          <p className="text-[17px] leading-[1.5] text-mute">
            약관에 동의하면 가입이 끝나요. 파우치와 메이크업 리포트가 이 계정에 저장돼요.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="gs-email" className="text-[16px] font-bold text-ink">
            이메일
          </label>
          <TextField
            id="gs-email"
            type="email"
            value={pendingSignup.email}
            readOnly
            className="bg-cream text-mute"
          />
        </div>

        <ProfileFields form={form} idPrefix="gs" />
        <AgreementFields form={form} />

        <div className="mt-auto flex shrink-0 flex-col gap-3 pt-2">
          {formErr && <Notice tone="error">{formErr}</Notice>}
          <PillButton type="submit" size="xl" className="w-full" busy={busy} disabled={!canSubmit}>
            {busy ? "가입 중" : "가입하기"}
          </PillButton>
        </div>
      </form>
    </main>
  );
}
