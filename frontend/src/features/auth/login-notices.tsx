import { Notice } from "@/components/ui/notice";

import { startGoogle } from "./login-google";
import type { LoginNoticeState } from "./use-login-notices";

/** 로그인 화면 위에 띄우는 안내(가입 완료·만료·재설정 완료·Google 로그인 결과) */
export function LoginNotices({
  notices,
  onEmail,
  onEmailFresh,
}: {
  notices: LoginNoticeState;
  /** 이메일 로그인 입력을 연다 */
  onEmail: () => void;
  /** 입력하던 비밀번호와 오류를 지우고 이메일 로그인 입력을 연다 */
  onEmailFresh: () => void;
}) {
  const { expired, signupDone, resetDone, google } = notices;
  return (
    <>
      {signupDone && <Notice tone="success">가입이 완료됐어요. 로그인해 주세요.</Notice>}
      {expired && (
        <Notice tone="expired" title="로그인이 만료됐어요. 다시 로그인해 주세요.">
          {expired === "tut"
            ? "진행 중이던 메이크업은 기록 없이 종료됐어요."
            : "다른 기기에서 같은 계정으로 로그인하면 이 기기는 로그아웃돼요."}
        </Notice>
      )}
      {resetDone && (
        <Notice tone="success">비밀번호를 바꿨어요. 새 비밀번호로 로그인해 주세요.</Notice>
      )}
      {google === "cancel" && <Notice tone="info">Google 로그인을 취소했어요.</Notice>}
      {google === "fail" && (
        <Notice
          tone="error"
          action={
            <button type="button" onClick={startGoogle}>
              다시 시도
            </button>
          }
        >
          Google 로그인에 실패했어요. 잠시 후 다시 시도해 주세요.
        </Notice>
      )}
      {google === "busy" && (
        <Notice tone="error">Google 로그인 시도가 너무 많아요. 잠시 후 다시 시도해 주세요.</Notice>
      )}
      {google === "unavailable" && (
        <Notice
          tone="error"
          action={
            <button type="button" onClick={onEmail}>
              이메일로 로그인
            </button>
          }
        >
          지금은 Google 로그인을 쓸 수 없어요. 이메일로 로그인해 주세요.
        </Notice>
      )}
      {google === "linked" && (
        <Notice
          tone="error"
          title="이미 가입된 이메일이에요"
          action={
            <button type="button" onClick={onEmailFresh}>
              이메일로 로그인
            </button>
          }
        >
          이 Google 계정의 이메일로 가입한 계정이 있어요. 자동으로 연결되지 않으니 이메일로 로그인해
          주세요.
        </Notice>
      )}
      {google === "expired" && (
        <Notice
          tone="info"
          action={
            <button type="button" onClick={startGoogle}>
              Google로 다시 시작
            </button>
          }
        >
          가입 시간이 지났어요. Google로 다시 시작해 주세요.
        </Notice>
      )}
    </>
  );
}
