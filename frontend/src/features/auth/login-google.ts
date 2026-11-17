import { apiUrl } from "@/lib/api";

/** Google 로그인 결과 안내. BE의 시작·복귀(callback)와 가입 화면이 /login?error=<코드>로 보낸다 */
export type GoogleNotice = "cancel" | "fail" | "busy" | "unavailable" | "linked" | "expired";

/** 서버 오류 코드를 안내 종류로 바꾼다. 목록에 없는 코드는 일반 실패로 안내한다 */
export function googleNotice(code: string): GoogleNotice {
  if (code === "USERS_GOOGLE_AUTH_CANCELLED") return "cancel";
  if (code === "USERS_ACCOUNT_LINK_REQUIRED") return "linked";
  if (code === "USERS_GOOGLE_SIGNUP_EXPIRED") return "expired";
  if (code === "USERS_GOOGLE_AUTH_UNAVAILABLE") return "unavailable";
  if (code === "USERS_LOGIN_RATE_LIMITED") return "busy";
  return "fail";
}

/** Google 로그인 시작. fetch가 아니라 화면 전체를 BE로 보내고, BE가 Google 인증 화면으로 넘긴다 */
export const startGoogle = () => window.location.assign(apiUrl("/v1/users/oauth/google"));
