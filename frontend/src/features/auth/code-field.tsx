"use client";

import { RotateCw } from "lucide-react";
import { useState, type ReactNode } from "react";

import { FieldError } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { TextField } from "@/components/ui/text-field";
import { ApiError, type CodeSent } from "@/lib/api";
import { mmss, useCountdown } from "@/lib/hooks/use-countdown";
import { cn } from "@/lib/utils";

/** 메일로 받은 6자리 인증번호와 남은 시간·다시 받기 대기. 가입 이메일 인증과 비밀번호 재설정이 같이 쓴다 */
export function useVerificationCode() {
  const [code, setCode] = useState("");
  /** 인증번호가 만료되는 시각 */
  const [codeUntil, setCodeUntil] = useState<number | null>(null);
  const [resendUntil, setResendUntil] = useState<number | null>(null);
  const codeLeft = useCountdown(codeUntil);
  const resendLeft = useCountdown(resendUntil);
  return {
    code,
    codeLeft,
    resendLeft,
    /** 6자리를 다 넣었고 시간이 남았다 */
    ready: code.length === 6 && codeLeft > 0,
    /** 숫자만 6자리까지 받는다 */
    input: (value: string) => setCode(value.replace(/\D/g, "").slice(0, 6)),
    /** 보냈다는 응답을 받으면 입력을 비우고 두 시계를 건다 */
    sent: (res: CodeSent) => {
      setCode("");
      setCodeUntil(Date.now() + res.expiresInSeconds * 1000);
      setResendUntil(Date.now() + res.resendAvailableInSeconds * 1000);
    },
    /** 요청 제한(429)이면 풀리는 시각까지 다시 받기를 막는다 */
    blockResend: (e: unknown) => {
      if (e instanceof ApiError && e.retryAfterSeconds) {
        setResendUntil(Date.now() + e.retryAfterSeconds * 1000);
      }
    },
    /** 확인에 쓴 인증번호는 서버에서 지워져 다시 쓸 수 없다. 입력과 남은 시간을 지워 다시 받게 한다 */
    clear: () => {
      setCode("");
      setCodeUntil(null);
    },
    /** 다시 받기 대기는 이메일마다 따로라, 이메일을 바꾸면 푼다 */
    resetResend: () => setResendUntil(null),
  };
}

export type VerificationCode = ReturnType<typeof useVerificationCode>;

/** 인증번호 입력 칸과 그 아래 남은 시간·다시 받기 줄 */
export function CodeField({
  code,
  id,
  noun,
  hint = "남은 시간",
  error,
  busy,
  side,
  inputClassName,
  onInput,
  onResend,
  onSubmit,
}: {
  code: VerificationCode;
  id?: string;
  /** 화면에서 부르는 이름 (인증번호 · 인증 코드) */
  noun: string;
  /** 남은 시간 앞 글자 */
  hint?: string;
  error?: string | null;
  /** 요청 중이면 다시 받기를 막는다 */
  busy: boolean;
  /** 입력 칸 오른쪽에 붙일 버튼 */
  side?: ReactNode;
  inputClassName?: string;
  /** 글자를 바꿀 때. 오류 문구를 지우는 데 쓴다 */
  onInput?: () => void;
  onResend: () => void;
  /** 6자리를 다 넣고 Enter를 누르면 */
  onSubmit?: () => void;
}) {
  return (
    <>
      <div className="flex gap-2.5">
        <TextField
          id={id}
          inputMode="numeric"
          maxLength={6}
          placeholder={`${noun} 6자리`}
          value={code.code}
          invalid={!!error}
          disabled={code.codeLeft === 0}
          onChange={(e) => {
            code.input(e.target.value);
            onInput?.();
          }}
          onKeyDown={(e) => {
            if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
            e.preventDefault();
            if (code.ready && !busy) onSubmit?.();
          }}
          autoComplete="one-time-code"
          className={cn("flex-1 tabular", inputClassName)}
        />
        {side}
      </div>
      {error && <FieldError>{error}</FieldError>}
      <div className="flex items-center justify-between gap-3 text-[15px] text-mute">
        {code.codeLeft > 0 ? (
          <span>
            {hint} <b className="text-navy tabular">{mmss(code.codeLeft)}</b>
          </span>
        ) : (
          <span className="text-error">{noun} 시간이 지났어요. 다시 받아 주세요.</span>
        )}
        {/* 대기 중에도 같은 자리에 비활성 버튼으로 둬서 줄이 흔들리지 않는다 */}
        <PillButton
          variant="outline"
          size="md"
          className="h-11 gap-1.5 border-line px-4 text-[15px]"
          onClick={onResend}
          disabled={busy || code.resendLeft > 0}
        >
          <RotateCw className="size-4" strokeWidth={2.2} aria-hidden />
          {code.resendLeft > 0 ? `${code.resendLeft}초 후 다시 받기` : "다시 받기"}
        </PillButton>
      </div>
    </>
  );
}
