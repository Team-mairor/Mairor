"use client";

import { Mail } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { FieldError, Notice } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { TextField } from "@/components/ui/text-field";
import { GoogleSheet, type GoogleResult } from "@/features/auth/google-sheet";
import { PasswordReset } from "@/features/auth/password-reset";
import { useCountdown } from "@/features/auth/use-countdown";
import { useSession } from "@/features/session";
import { useQuery } from "@/lib/use-query";
import { isValidEmail } from "@/lib/validation";

type Mode = "pick" | "email" | "reset";

// ponytail: 시도 제한은 프로토타입 시연값(3회 · 30초). 실제 값은 서버 429의 Retry-After를 쓴다.
const LOCK_AFTER = 3;
const LOCK_SEC = 30;

/** 01 로그인 (USERS-002·003·004·005). ?expired=basic|tut, ?signup=done&email= 로 안내를 띄운다 */
export default function LoginPage() {
  const router = useRouter();
  const query = useQuery();
  const { state, update } = useSession();

  const [mode, setMode] = useState<Mode>("pick");
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [credErr, setCredErr] = useState(false);
  const [fails, setFails] = useState(0);
  const [lockUntil, setLockUntil] = useState<number | null>(null);
  const [expired, setExpired] = useState<"basic" | "tut" | null>(null);
  const [signupDone, setSignupDone] = useState(false);
  const [resetDone, setResetDone] = useState(false);
  const [google, setGoogle] = useState(false);
  const [gNotice, setGNotice] = useState<Exclude<GoogleResult, "ok"> | null>(null);
  const [linkedEmail, setLinkedEmail] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const lockLeft = useCountdown(lockUntil);
  const canLogin = !!email.trim() && !!pw && !busy && lockLeft === 0;

  useEffect(() => {
    if (!query) return;
    const ex = query.get("expired");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 안내를 한 번 반영한다
    if (ex === "basic" || ex === "tut") setExpired(ex);
    if (query.get("signup") === "done") {
      setSignupDone(true);
      setEmail(query.get("email") ?? "");
      setMode("email");
    }
    if (query.get("mode") === "email") setMode("email");
  }, [query]);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  /** 로그인 성공. 이 기기에서 온보딩을 안 봤으면 온보딩으로 (POUCH-001) */
  const finish = (who: string) => {
    update({ loggedIn: true, email: who });
    router.replace(state.onboarded ? "/home" : "/onboarding");
  };

  // ponytail: API-USERS-002 대신 형식·길이만 본다. 실패 횟수 초과 시 잠금.
  const submit = () => {
    if (!canLogin) return;
    setBusy(true);
    setCredErr(false);
    timer.current = setTimeout(() => {
      const ok = isValidEmail(email) && pw.length >= 8;
      setBusy(false);
      if (ok) return finish(email.trim().toLowerCase());
      const f = fails + 1;
      if (f >= LOCK_AFTER) {
        setFails(0);
        setLockUntil(Date.now() + LOCK_SEC * 1000);
      } else {
        setFails(f);
        setCredErr(true);
      }
    }, 700);
  };

  const onGoogle = (r: GoogleResult, who?: string) => {
    setGoogle(false);
    if (r === "ok") return finish(who ?? "");
    if (r === "linked") setLinkedEmail(who ?? "");
    setGNotice(r);
  };

  const openEmail = () => {
    setMode("email");
    setGNotice(null);
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
      </div>

      <div className="flex shrink-0 flex-col gap-8 px-10 py-8">
        {mode === "pick" && (
          <div className="flex flex-col gap-4">
            <span className="font-serif text-[120px] leading-[.85] tracking-[-.03em] text-plum italic">
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
            <span className="font-serif text-[30px] leading-none text-plum italic">mairor</span>
            <h1 className="font-display text-[40px] leading-[1.25] text-ink">이메일로 로그인</h1>
            <p className="text-[17px] leading-[1.5] text-mute">
              가입할 때 쓴 이메일과 비밀번호를 입력해 주세요.
            </p>
          </div>
        )}

        {mode === "reset" ? (
          <PasswordReset
            initialEmail={email}
            onBack={() => setMode("email")}
            onDone={(who) => {
              setEmail(who);
              setPw("");
              setCredErr(false);
              setFails(0);
              setLockUntil(null);
              setResetDone(true);
              setMode("email");
            }}
          />
        ) : (
          <div className="flex flex-col gap-4">
            {signupDone && <Notice tone="success">가입이 완료됐어요. 로그인해 주세요.</Notice>}
            {expired && (
              <Notice tone="expired" title="로그인이 만료됐어요. 다시 로그인해 주세요.">
                {expired === "tut" ? "진행 중이던 메이크업은 기록 없이 종료됐어요." : undefined}
              </Notice>
            )}
            {resetDone && (
              <Notice tone="success">비밀번호를 바꿨어요. 새 비밀번호로 로그인해 주세요.</Notice>
            )}
            {gNotice === "cancel" && <Notice tone="info">Google 로그인을 취소했어요.</Notice>}
            {gNotice === "fail" && (
              <Notice
                tone="error"
                action={
                  <button type="button" onClick={() => setGoogle(true)}>
                    다시 시도
                  </button>
                }
              >
                Google 로그인에 실패했어요. 잠시 후 다시 시도해 주세요.
              </Notice>
            )}
            {gNotice === "linked" && (
              <Notice
                tone="error"
                title="이미 이메일로 가입된 계정이에요"
                action={
                  <button
                    type="button"
                    onClick={() => {
                      setEmail(linkedEmail);
                      setPw("");
                      setCredErr(false);
                      openEmail();
                    }}
                  >
                    이메일로 로그인
                  </button>
                }
              >
                {linkedEmail}은 이메일 로그인으로 가입돼 있어요. Google 계정과 자동으로 연결되지
                않으니 이메일로 로그인해 주세요.
              </Notice>
            )}

            {mode === "pick" && (
              <div className="grid grid-cols-2 gap-3">
                <PillButton onClick={openEmail}>
                  <Mail className="size-5" strokeWidth={1.9} aria-hidden />
                  이메일로 로그인
                </PillButton>
                <PillButton
                  variant="outline"
                  onClick={() => {
                    setGNotice(null);
                    setSignupDone(false);
                    setGoogle(true);
                  }}
                >
                  <span className="font-label text-[22px] font-bold">G</span>
                  Google로 계속하기
                </PillButton>
              </div>
            )}

            {mode === "email" && (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <TextField
                  type="email"
                  placeholder="이메일"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setCredErr(false);
                  }}
                  autoComplete="email"
                />
                <TextField
                  type="password"
                  placeholder="비밀번호"
                  value={pw}
                  onChange={(e) => {
                    setPw(e.target.value);
                    setCredErr(false);
                  }}
                  autoComplete="current-password"
                />
                {credErr && lockLeft === 0 && (
                  <FieldError>이메일 또는 비밀번호를 확인해 주세요.</FieldError>
                )}
                {lockLeft > 0 && (
                  <Notice tone="locked">
                    <span>
                      로그인 시도가 너무 많아요. <b className="tabular">{lockLeft}초</b> 후에 다시
                      시도해 주세요.
                    </span>
                  </Notice>
                )}
                <button
                  type="button"
                  className="self-end text-[16px] text-mute underline"
                  onClick={() => {
                    setMode("reset");
                    setSignupDone(false);
                    setResetDone(false);
                    setCredErr(false);
                  }}
                >
                  비밀번호를 잊었어요
                </button>
                <div className="mt-1 flex gap-3">
                  <IconButton
                    type="button"
                    onClick={() => setMode("pick")}
                    title="다른 방법으로 로그인"
                    aria-label="다른 방법으로 로그인"
                  />
                  <PillButton type="submit" className="flex-1" busy={busy} disabled={!canLogin}>
                    {busy ? "확인 중" : lockLeft > 0 ? `${lockLeft}초 후 다시 시도` : "로그인"}
                  </PillButton>
                </div>
              </form>
            )}

            <div className="flex justify-center gap-2 text-[17px]">
              <span className="text-mute">아직 계정이 없나요?</span>
              <Link href="/signup" className="font-bold text-plum">
                이메일로 회원가입
              </Link>
            </div>
          </div>
        )}
      </div>

      {google && <GoogleSheet onResult={onGoogle} />}
    </main>
  );
}
