"use client";

import { STORAGE_KEYS, isObject } from "./storage";
import { createStore } from "./store";

export interface AuthState {
  loggedIn: boolean;
  email: string;
  /** 서버의 닉네임. 없으면 "" */
  nickname: string;
  /** 로그아웃하지 않았는데 세션이 끝남. 다음 로그인 전까지 인트로가 만료 안내로 보낸다 */
  sessionExpired: boolean;
}

export const EMPTY_AUTH: AuthState = {
  loggedIn: false,
  email: "",
  nickname: "",
  sessionExpired: false,
};

function parseAuth(raw: unknown): AuthState | undefined {
  if (!isObject(raw)) return undefined;
  return {
    loggedIn: raw.loggedIn === true,
    email: typeof raw.email === "string" ? raw.email : "",
    nickname: typeof raw.nickname === "string" ? raw.nickname : "",
    sessionExpired: raw.sessionExpired === true,
  };
}

export const authStore = createStore("useAuth", STORAGE_KEYS.auth, EMPTY_AUTH, parseAuth);

/** 로그인 상태. 바꾸는 쪽은 useSessionActions의 signIn·signOut·expireSession뿐이다 */
export function useAuth(): AuthState {
  return authStore.useStore().value;
}

/** 화면에서 부르는 이름. 닉네임이 없으면 이메일 앞부분 */
export function displayName({ nickname, email }: Pick<AuthState, "nickname" | "email">) {
  return nickname || email.split("@")[0];
}
