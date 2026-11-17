"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useSession } from "./session-provider";

/**
 * 로그인이 끊긴 것을 알게 되면 로그인 화면으로 보낸다. 회원 화면(하단 탭 묶음)에 둔다.
 * 계정당 로그인 세션은 하나라서, 다른 기기에서 같은 계정으로 로그인하면 이 기기의 다음 요청은 401이 된다.
 * 401을 받은 곳이 로그인 상태를 끄면(expireSession) 그 자리에 빈 화면으로 남지 않게 여기서 옮긴다.
 */
export function ExpiredSessionRedirect() {
  const router = useRouter();
  const { state, sessionChecked } = useSession();
  const expired = sessionChecked && !state.loggedIn && state.sessionExpired;

  useEffect(() => {
    if (expired) router.replace("/login?expired=basic");
  }, [expired, router]);

  return null;
}
