"use client";

import { Mail } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { FieldError } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { TextField } from "@/components/ui/text-field";
import { isValidEmail, passwordRule } from "@/lib/validation";

import { useCountdown } from "./use-countdown";

export type ResetStep = "email" | "code" | "pw";

const SUBTITLE: Record<ResetStep, (email: string) => string> = {
  email: () => "가입한 이메일을 입력하면 인증 코드를 보내 드려요.",
  code: (email) =>
    `${email}(으)로 6자리 인증 코드를 보냈어요. 메일이 안 보이면 스팸함도 확인해 주세요.`,
  pw: () => "새로 쓸 비밀번호를 입력해 주세요.",
};
const STEP_NO: Record<ResetStep, number> = { email: 1, code: 2, pw: 3 };

/** 코드 재발송 간격(초). USERS-005 */
const RESEND_SEC = 60;

/**
 * 비밀번호 재설정 3단계 (USERS-005). 이메일 → 인증 코드 → 새 비밀번호.
 * ponytail: API-USERS-008~010이 없어 코드 발송·확인을 흉내 낸다. 발송된 코드는 화면 위 메일 알림으로 보여 준다.
 */
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
  const [code, setCode] = useState("");
  const [sentCode, setSentCode] = useState("");
  const [codeErr, setCodeErr] = useState(false);
  const [mail, setMail] = useState(false);
  const [resendUntil, setResendUntil] = useState<number | null>(null);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const resendLeft = useCountdown(resendUntil);
  const emailOk = isValidEmail(email);
  const pwOk = passwordRule(pw).ok;

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  // 화면을 떠나면 대기 중인 흉내 응답은 버린다
  useEffect(() => clearTimers, []);

  // 서버 왕복을 흉내 내는 지연
  const wait = (ms: number, fn: () => void) => {
    setBusy(true);
    timers.current.push(
      setTimeout(() => {
        setBusy(false);
        fn();
      }, ms),
    );
  };

  const send = () => {
    const c = String(Math.floor(100000 + Math.random() * 900000));
    setSentCode(c);
    setCode("");
    setCodeErr(false);
    setMail(false);
    setStep("code");
    setResendUntil(Date.now() + RESEND_SEC * 1000);
    timers.current.push(setTimeout(() => setMail(true), 1200));
  };

  const back = () => {
    clearTimers();
    setBusy(false);
    setMail(false);
    if (step === "pw") setStep("code");
    else if (step === "code") setStep("email");
    else onBack();
  };

  const verify = () => {
    wait(700, () => {
      if (code === sentCode) {
        setStep("pw");
        setMail(false);
        setPw("");
        setPw2("");
      } else setCodeErr(true);
    });
  };

  return (
    <>
      <div className="flex flex-col gap-2.5">
        <span className="font-serif text-[30px] leading-none text-plum italic">mairor</span>
        <div className="flex items-baseline gap-3.5">
          <h1 className="font-display text-[40px] leading-[1.25] text-ink">비밀번호 재설정</h1>
          <span className="font-label text-[15px] font-semibold tracking-[.12em] text-plum tabular">
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
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
            <span className="text-[15px] leading-[1.5] text-mute">
              Google로 가입했다면 비밀번호 없이 &apos;Google로 계속하기&apos;로 로그인해 주세요.
            </span>
            <div className="mt-1 flex gap-3">
              <IconButton onClick={back} title="이전" aria-label="이전" />
              <PillButton
                className="flex-1"
                busy={busy}
                disabled={!emailOk}
                onClick={() => wait(800, send)}
              >
                {busy ? "보내는 중" : "인증 코드 받기"}
              </PillButton>
            </div>
          </>
        )}

        {step === "code" && (
          <>
            <TextField
              inputMode="numeric"
              maxLength={6}
              placeholder="인증 코드 6자리"
              value={code}
              onChange={(e) => {
                setCode(e.target.value.replace(/\D/g, "").slice(0, 6));
                setCodeErr(false);
              }}
              className="text-[22px] font-semibold tracking-[.3em] tabular"
              autoComplete="one-time-code"
            />
            {codeErr && (
              <FieldError>인증 코드가 맞지 않아요. 메일의 코드를 다시 확인해 주세요.</FieldError>
            )}
            <div className="flex items-center justify-between gap-3 text-[15px] text-mute">
              <span>코드는 10분 동안 유효해요</span>
              {resendLeft > 0 ? (
                <span className="tabular">{resendLeft}초 후 다시 받기</span>
              ) : (
                <button
                  type="button"
                  className="font-bold text-plum"
                  onClick={() => wait(600, send)}
                  disabled={busy}
                >
                  코드 다시 받기
                </button>
              )}
            </div>
            <div className="mt-1 flex gap-3">
              <IconButton onClick={back} title="이전" aria-label="이전" />
              <PillButton
                className="flex-1"
                busy={busy}
                disabled={code.length !== 6}
                onClick={verify}
              >
                {busy ? "확인 중" : "확인"}
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
              onChange={(e) => setPw(e.target.value)}
              autoComplete="new-password"
            />
            <span
              className={`text-[15px] ${!pw ? "text-mute" : pwOk ? "text-lime-ink" : "text-wine"}`}
            >
              8~64자 · 영문·숫자·특수문자 포함
            </span>
            <TextField
              type="password"
              placeholder="새 비밀번호 확인"
              value={pw2}
              onChange={(e) => setPw2(e.target.value)}
              autoComplete="new-password"
            />
            {!!pw2 && pw !== pw2 && <FieldError>비밀번호가 서로 달라요.</FieldError>}
            <div className="mt-1 flex gap-3">
              <IconButton onClick={back} title="이전" aria-label="이전" />
              <PillButton
                className="flex-1"
                busy={busy}
                disabled={!pwOk || pw !== pw2}
                onClick={() => wait(800, () => onDone(email.trim()))}
              >
                {busy ? "바꾸는 중" : "비밀번호 바꾸기"}
              </PillButton>
            </div>
          </>
        )}
      </div>

      {/* 흉내 낸 메일 알림. 탭하면 코드가 채워진다 */}
      {step === "code" && mail && (
        <button
          type="button"
          onClick={() => {
            setCode(sentCode);
            setCodeErr(false);
            setMail(false);
          }}
          className="absolute inset-x-6 top-4 z-10 flex animate-fade items-center gap-3.5 rounded-[22px] bg-white px-[18px] py-4 text-left shadow-[0_18px_40px_rgba(20,4,12,.22)]"
        >
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-cream">
            <Mail className="size-[22px] text-ink" strokeWidth={1.9} aria-hidden />
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="flex justify-between gap-2.5 text-[14px] text-mute">
              <span>Gmail · mairor</span>
              <span>지금</span>
            </span>
            <span className="text-[16px] font-bold text-ink">
              [mairor] 비밀번호 재설정 인증 코드
            </span>
            <span className="text-[15px] text-ink">
              인증 코드 <b className="tracking-[.12em] tabular">{sentCode}</b> · 10분 동안 유효해요
            </span>
          </span>
        </button>
      )}
    </>
  );
}
