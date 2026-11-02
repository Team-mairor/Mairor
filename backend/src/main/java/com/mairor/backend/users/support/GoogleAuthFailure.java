package com.mairor.backend.users.support;

/**
 * Google 로그인 callback 이 실패했을 때 로그인 화면({@code /login?error=<코드>})에 넘기는 코드. FE 는 이 목록만 분기하고, 목록에 없는
 * 값은 일반 실패로 안내한다. Google 이 보낸 오류 문구·code·토큰은 넘기지 않는다.
 *
 * <p>{@link #ACCOUNT_LINK_REQUIRED}·{@link #UNAVAILABLE} 은 가입 완료·로그인 시작의 JSON 오류(409·503)에도 같은 코드로
 * 쓴다.
 */
public enum GoogleAuthFailure {
  /** 사용자가 Google 화면에서 취소했다 ({@code error=access_denied}). */
  CANCELLED("USERS_GOOGLE_AUTH_CANCELLED"),
  /** 코드 교환·ID 토큰 검증 실패, 확인되지 않은 이메일, 그 밖의 Google 오류. */
  FAILED("USERS_GOOGLE_AUTH_FAILED"),
  /** 로그인 시작 기록이 없음·만료·재사용·state 불일치. */
  STATE_INVALID("USERS_OAUTH_STATE_INVALID"),
  /** 같은 이메일의 다른 계정이 있다. 자동으로 연결하지 않는다. */
  ACCOUNT_LINK_REQUIRED("USERS_ACCOUNT_LINK_REQUIRED"),
  /** 설정이 없거나 Google 에 연결할 수 없다. */
  UNAVAILABLE("USERS_GOOGLE_AUTH_UNAVAILABLE");

  private final String code;

  GoogleAuthFailure(String code) {
    this.code = code;
  }

  public String code() {
    return code;
  }
}
