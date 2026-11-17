"use client";

import { useState } from "react";

import { passwordRule } from "@/lib/validation";

/** 회원가입의 비밀번호와 확인 입력. 서버가 알려 준 오류는 칸을 고칠 때까지 보여 준다 */
export function useSignupPassword() {
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [pwError, setPwError] = useState<string | null>(null);
  const [pw2Error, setPw2Error] = useState<string | null>(null);

  const rule = passwordRule(pw);
  const match = pw2.length > 0 && pw === pw2;

  return {
    pw,
    pw2,
    rule,
    match,
    pwError,
    pw2Error,
    changePw: (value: string) => {
      setPw(value);
      setPwError(null);
    },
    changePw2: (value: string) => {
      setPw2(value);
      setPw2Error(null);
    },
    setErrors: (pwReason: string | null, pw2Reason: string | null) => {
      setPwError(pwReason);
      setPw2Error(pw2Reason);
    },
    clearErrors: () => {
      setPwError(null);
      setPw2Error(null);
    },
  };
}

export type SignupPassword = ReturnType<typeof useSignupPassword>;
