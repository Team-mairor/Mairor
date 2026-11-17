"use client";

import { Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { PillButton } from "@/components/ui/pill-button";
import { useDevice, useSessionActions } from "@/domain/session";
import type { User } from "@/lib/api";

import { LoginEmailForm } from "./login-email-form";
import { startGoogle } from "./login-google";
import { LoginNotices } from "./login-notices";
import { PasswordReset } from "./password-reset";
import { useLoginForm } from "./use-login-form";
import { useLoginNotices } from "./use-login-notices";

type Mode = "pick" | "email" | "reset";

/** 로그인. ?expired=basic|tut, ?signup=done&email=, ?error=<Google 오류 코드>로 안내를 띄운다 */
export function LoginView() {
  const router = useRouter();
  const { onboarded } = useDevice();
  const { signIn } = useSessionActions();
  const [mode, setMode] = useState<Mode>("pick");

  /** 로그인 성공. 이 기기에서 온보딩을 안 봤으면 온보딩으로 */
  const finish = (user: Pick<User, "email" | "nickname">, csrfToken?: string) => {
    signIn(user, csrfToken);
    router.replace(onboarded ? "/home" : "/onboarding");
  };

  const form = useLoginForm({ onSuccess: finish });
  const notices = useLoginNotices({
    onEmailLink: (email) => {
      form.prefillEmail(email);
      setMode("email");
    },
  });

  const openEmail = () => {
    setMode("email");
    notices.dismissGoogle();
  };

  return (
    <main className="relative flex flex-1 flex-col bg-white">
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {/* eslint-disable-next-line @next/next/no-img-element -- 정적 내보내기라 next/image 최적화를 쓰지 않는다 */}
        <img
          src="/images/login-editorial.png"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[50%_28%]"
        />
        <span className="absolute bottom-7 left-10 rounded-full bg-white px-4 py-[9px] font-label text-[15px] font-semibold tracking-[.16em] text-ink">
          AI MAKEUP MIRROR
        </span>
        <MirrorToggle fitFirst className="absolute top-7 right-10" />
      </div>

      <div className="flex shrink-0 flex-col gap-8 px-10 py-8">
        {mode === "pick" && (
          <div className="flex flex-col gap-4">
            <span className="font-serif text-[120px] leading-[.85] tracking-[-.03em] text-navy italic">
              mairor
            </span>
            <div className="flex flex-col gap-1.5">
              <h1 className="font-display text-[26px] leading-[1.35] text-ink">
                따라 하고 싶은 메이크업을 내 얼굴 위에 그대로
              </h1>
              <span className="font-serif text-[22px] leading-[1.2] text-mute italic">
                Your mirror, your makeup artist.
              </span>
            </div>
          </div>
        )}
        {mode === "email" && (
          <div className="flex flex-col gap-2.5">
            <span className="font-serif text-[30px] leading-none text-navy italic">mairor</span>
            <h1 className="font-display text-[40px] leading-[1.25] text-ink">이메일로 로그인</h1>
            <p className="text-[17px] leading-[1.5] text-mute">
              가입할 때 쓴 이메일과 비밀번호를 입력해 주세요.
            </p>
          </div>
        )}

        {mode === "reset" ? (
          <PasswordReset
            initialEmail={form.email}
            onBack={() => setMode("email")}
            onDone={(who) => {
              form.finishReset(who);
              notices.markResetDone();
              setMode("email");
            }}
          />
        ) : (
          <div className="flex flex-col gap-4">
            <LoginNotices
              notices={notices}
              onEmail={openEmail}
              onEmailFresh={() => {
                form.clearPassword();
                openEmail();
              }}
            />

            {mode === "pick" && (
              <div className="grid grid-cols-2 gap-3">
                <PillButton onClick={openEmail}>
                  <Mail className="size-5" strokeWidth={1.9} aria-hidden />
                  이메일로 로그인
                </PillButton>
                <PillButton variant="outline" onClick={startGoogle}>
                  <span className="font-label text-[22px] font-bold">G</span>
                  Google로 계속하기
                </PillButton>
              </div>
            )}

            {mode === "email" && (
              <LoginEmailForm
                form={form}
                onForgot={() => {
                  setMode("reset");
                  notices.clearDone();
                  form.clearError();
                }}
                onBack={() => setMode("pick")}
              />
            )}

            <div className="flex justify-center gap-2 text-[17px]">
              <span className="text-mute">아직 계정이 없나요?</span>
              <Link href="/signup" className="font-bold text-navy">
                이메일로 회원가입
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
