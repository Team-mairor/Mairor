package com.mairor.backend.common.security;

/** 로그인 세션이 끝나는 이유. {@link SessionEndHook} 구현이 이유별로 다르게 처리할 수 있게 알려 준다. 지표 라벨 값은 이름의 소문자다. */
public enum SessionEndReason {
  /** 회원이 로그아웃했다. */
  LOGOUT,
  /** 비밀번호 재설정이 이 회원의 모든 세션을 끊었다. */
  ALL_DEVICES_REVOKED,
  /** 새 로그인이 이전 인증 세션을 대체했다(같은 계정의 다른 기기 로그인, 같은 브라우저의 재로그인·계정 전환). */
  REPLACED_BY_LOGIN,
  /** 로그인한 지 절대 만료 시간이 지나 활동 중이어도 끝났다. */
  ABSOLUTE_EXPIRED,
  /** 마지막 요청으로부터 유휴 만료 시간이 지나 끝났다. */
  IDLE_EXPIRED
}
