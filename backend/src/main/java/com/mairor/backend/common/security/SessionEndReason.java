package com.mairor.backend.common.security;

/** 로그인 세션이 끝나는 이유. {@link SessionEndHook} 구현이 이유별로 다르게 처리할 수 있게 알려 준다. 지표 라벨 값은 이름의 소문자다. */
public enum SessionEndReason {
  /** 회원이 현재 기기에서 로그아웃했다. 기기 목록에서 현재 기기를 지정해 지운 경우도 포함한다. */
  LOGOUT,
  /** 회원이 다른 기기의 로그인을 끊었다. */
  DEVICE_REVOKED,
  /** 모든 기기를 끊는 요청(전체 로그아웃, 이후 비밀번호 재설정)으로 끝났다. */
  ALL_DEVICES_REVOKED,
  /** 같은 브라우저에서 다시 로그인하거나 다른 계정으로 전환해서 이전 인증 세션이 대체됐다. */
  REPLACED_BY_LOGIN,
  /** 로그인한 지 절대 만료 시간이 지나 활동 중이어도 끝났다. */
  ABSOLUTE_EXPIRED,
  /** 마지막 요청으로부터 유휴 만료 시간이 지나 끝났다. */
  IDLE_EXPIRED
}
