"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useSession } from "@/features/session";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useRequest } from "@/lib/hooks/use-request";

/** 로그아웃 (API-USERS-003). 끝나면 로그인 화면으로 보낸다. 세션이 이미 끝났으면(401) 로그아웃된 것으로 본다 */
export function useLogout() {
  const router = useRouter();
  const { signOut } = useSession();
  const { pending, run } = useRequest<"logout">();
  const [error, setError] = useState<string | null>(null);

  const done = () => {
    signOut();
    router.replace("/login");
  };

  const logout = () => {
    setError(null);
    return run(
      "logout",
      async (signal) => {
        await api.post("/v1/users/logout", { signal });
        done();
      },
      (e) => {
        if (e instanceof ApiError && e.code === "UNAUTHORIZED") return done();
        setError(errorMessage(e));
      },
    );
  };

  return { logout, pending: pending !== null, error };
}
