"use client";

import { Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { PillButton } from "@/components/ui/pill-button";
import { Spinner } from "@/components/ui/spinner";
import { TextField } from "@/components/ui/text-field";
import { EXISTING_EMAILS } from "@/lib/mock-data";
import { cn } from "@/lib/utils";
import {
  isValidEmail,
  normalizeEmail,
  passwordBytes,
  PASSWORD_MAX_BYTES,
  passwordRule,
} from "@/lib/validation";

const AGREEMENTS = [
  { key: "terms", label: "[필수] 서비스 이용약관" },
  { key: "privacy", label: "[필수] 개인정보 수집·이용 동의" },
] as const;
type AgreeKey = (typeof AGREEMENTS)[number]["key"];

type EmailCheck = "idle" | "busy" | "ok";
/** dup: 이미 가입된 이메일, msg: 서버가 준 안내 문구 */
type EmailError = { kind: "dup" } | { kind: "msg"; text: string } | null;

function RuleItem({ ok, children }: { ok: boolean; children: string }) {
  return (
    <span className={cn("flex items-center gap-1.5", ok ? "text-plum" : "text-ash-2")}>
      <Check className="size-3.5" strokeWidth={3} aria-hidden />
      {children}
    </span>
  );
}

/** 01-1 회원가입 (USERS-001). 이메일 중복 확인 → 비밀번호 규칙 → 약관 동의 → 가입 */
export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [agree, setAgree] = useState<Record<AgreeKey, boolean>>({ terms: false, privacy: false });
  const [check, setCheck] = useState<EmailCheck>("idle");
  const [checkedFor, setCheckedFor] = useState("");
  const [emailErr, setEmailErr] = useState<EmailError>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  const emN = normalizeEmail(email);
  const emailOk = isValidEmail(email);
  const rule = passwordRule(pw);
  const match = pw2.length > 0 && pw === pw2;
  const allAgreed = AGREEMENTS.every((a) => agree[a.key]);
  // 이메일을 바꾸면 중복 확인을 다시 해야 한다
  const chk: EmailCheck = checkedFor === emN ? check : "idle";
  const canCheck = emailOk && chk === "idle";
  const canSubmit = emailOk && chk === "ok" && rule.ok && match && allAgreed && !busy;

  // ponytail: API-USERS-011 대신 샘플 계정 목록과 비교한다
  const checkEmail = () => {
    if (!canCheck) return;
    setCheck("busy");
    setCheckedFor(emN);
    setEmailErr(null);
    timer.current = setTimeout(() => {
      if (EXISTING_EMAILS.includes(emN)) {
        setCheck("idle");
        setEmailErr({ kind: "dup" });
      } else setCheck("ok");
    }, 600);
  };

  const submit = () => {
    if (!canSubmit) return;
    setBusy(true);
    setEmailErr(null);
    setPwErr(null);
    timer.current = setTimeout(() => {
      setBusy(false);
      // 가입 시점의 409는 동시 가입 대비로 유지한다
      if (EXISTING_EMAILS.includes(emN)) {
        setCheck("idle");
        setEmailErr({ kind: "dup" });
        return;
      }
      if (passwordBytes(pw) > PASSWORD_MAX_BYTES) {
        setPwErr("비밀번호가 너무 길어요. 한글은 영문보다 길게 계산돼요(72바이트 이하).");
        return;
      }
      router.replace(`/login?signup=done&email=${encodeURIComponent(emN)}`);
    }, 800);
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
        <span className="font-serif text-[28px] leading-none text-plum italic">Sign up</span>
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
                }}
                autoComplete="email"
                className="flex-1"
              />
              <button
                type="button"
                onClick={checkEmail}
                disabled={!canCheck && chk !== "busy"}
                className={cn(
                  "flex h-[60px] shrink-0 items-center justify-center gap-2 rounded-2xl border px-5 text-[17px] font-semibold whitespace-nowrap",
                  chk === "ok"
                    ? "border-lime bg-lime-pale text-lime-ink"
                    : canCheck
                      ? "border-plum bg-white text-plum"
                      : "border-line-2 bg-white text-ash-2",
                )}
              >
                {chk === "busy" && (
                  <Spinner tone="brand" className="size-4 border-pink-soft border-t-plum" />
                )}
                {chk === "busy" ? "확인 중" : chk === "ok" ? "확인 완료" : "중복 확인"}
              </button>
            </div>
            {emailBad && (
              <span className="text-[15px] text-wine-2">이메일 형식을 확인해 주세요.</span>
            )}
            {chk === "ok" && !emailErr && (
              <span className="flex items-center gap-1.5 text-[15px] text-lime-ink">
                <Check className="size-3.5" strokeWidth={3} aria-hidden />
                사용할 수 있는 이메일이에요.
              </span>
            )}
            {emailOk && chk === "idle" && !emailErr && rule.ok && match && (
              <span className="text-[15px] text-mute">이메일 중복 확인을 해 주세요.</span>
            )}
            {emailErr?.kind === "dup" && (
              <span className="flex flex-wrap items-center gap-2.5 text-[15px] text-wine-2">
                <span>이미 가입된 이메일이에요.</span>
                <button
                  type="button"
                  className="font-bold text-plum underline"
                  onClick={() => router.push(`/login?mode=email&email=${encodeURIComponent(emN)}`)}
                >
                  로그인하기
                </button>
              </span>
            )}
            {emailErr?.kind === "msg" && (
              <span className="text-[15px] text-wine-2">{emailErr.text}</span>
            )}
          </div>

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
            </div>
            {pwErr && <span className="text-[15px] text-wine-2">{pwErr}</span>}
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
              invalid={pw2.length > 0 && !match}
              onChange={(e) => setPw2(e.target.value)}
              autoComplete="new-password"
            />
            {pw2.length > 0 && !match && (
              <span className="text-[15px] text-wine-2">비밀번호가 일치하지 않아요.</span>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-3.5 border-t border-line pt-6">
          <button
            type="button"
            onClick={() =>
              setAgree(
                allAgreed ? { terms: false, privacy: false } : { terms: true, privacy: true },
              )
            }
            className="flex items-center gap-3 text-[18px] font-bold text-ink"
            aria-pressed={allAgreed}
          >
            <span
              className={cn(
                "flex size-[26px] shrink-0 items-center justify-center rounded-lg border-[1.5px] text-white",
                allAgreed ? "border-pink bg-pink" : "border-ash-2 bg-white",
              )}
            >
              <Check className="size-4" strokeWidth={3} aria-hidden />
            </span>
            전체 동의
          </button>
          {AGREEMENTS.map((a) => (
            <div key={a.key} className="flex items-center gap-3 pl-1 text-[16px] text-ink">
              <button
                type="button"
                onClick={() => setAgree((p) => ({ ...p, [a.key]: !p[a.key] }))}
                aria-pressed={agree[a.key]}
                className="flex flex-1 items-center gap-3 text-left"
              >
                <span
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center",
                    agree[a.key] ? "text-pink" : "text-line-3",
                  )}
                >
                  <Check className="size-[18px]" strokeWidth={2.6} aria-hidden />
                </span>
                <span className="flex-1">{a.label}</span>
              </button>
              {/* TODO: 약관 원문 정적 페이지 연결 */}
              <span className="text-[15px] text-mute underline">보기</span>
            </div>
          ))}
        </div>

        <div className="mt-auto shrink-0 pt-2">
          <PillButton type="submit" size="xl" className="w-full" busy={busy} disabled={!canSubmit}>
            {busy ? "가입 중" : "가입하기"}
          </PillButton>
        </div>
      </form>
    </main>
  );
}
