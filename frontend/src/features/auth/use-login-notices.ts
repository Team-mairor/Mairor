"use client";

import { useEffect, useState } from "react";

import { useQuery } from "@/lib/hooks/use-query";

import { googleNotice, type GoogleNotice } from "./login-google";

/**
 * 주소로 받은 안내. ?expired=basic|tut, ?signup=done&email=, ?error=<Google 오류 코드>를 읽어 한 번 반영한다.
 * 가입을 마쳤거나 ?mode=email이면 이메일 로그인으로 열도록 onEmailLink에 이메일을 넘긴다
 */
export function useLoginNotices({ onEmailLink }: { onEmailLink: (email: string) => void }) {
  const query = useQuery();
  const [expired, setExpired] = useState<"basic" | "tut" | null>(null);
  const [signupDone, setSignupDone] = useState(false);
  const [resetDone, setResetDone] = useState(false);
  const [google, setGoogle] = useState<GoogleNotice | null>(null);

  useEffect(() => {
    if (!query) return;
    const ex = query.get("expired");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 안내를 한 번 반영한다
    if (ex === "basic" || ex === "tut") setExpired(ex);
    if (query.get("signup") === "done") setSignupDone(true);
    if (query.get("signup") === "done" || query.get("mode") === "email") {
      onEmailLink(query.get("email") ?? "");
    }
    const googleError = query.get("error");
    if (googleError) setGoogle(googleNotice(googleError));
    // onEmailLink는 렌더마다 새로 만들어져도 주소가 바뀔 때만 반영한다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  return {
    expired,
    signupDone,
    resetDone,
    google,
    dismissGoogle: () => setGoogle(null),
    markResetDone: () => setResetDone(true),
    /** 비밀번호 재설정으로 들어가면 가입·재설정 완료 안내는 닫는다 */
    clearDone: () => {
      setSignupDone(false);
      setResetDone(false);
    },
  };
}

export type LoginNoticeState = ReturnType<typeof useLoginNotices>;
