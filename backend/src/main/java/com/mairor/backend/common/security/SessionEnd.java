package com.mairor.backend.common.security;

import java.util.Objects;

/**
 * 끝나려는 로그인 세션 하나. {@link SessionEndHook} 에 전달된다.
 *
 * <p>{@code sessionId} 는 세션 쿠키 값과 연결되는 비밀 값이다. 로그·지표·응답에 내보내지 않는다. {@link #toString()} 도 이 값을 가린다.
 *
 * @param userId 세션 주인의 회원 ID (세션의 {@code PRINCIPAL_NAME})
 * @param sessionId 저장소의 세션 ID. 이 세션에 묶인 데이터(예: 진행 중인 가이드 실행)를 찾는 기준이다
 * @param reason 끝나는 이유
 */
public record SessionEnd(String userId, String sessionId, SessionEndReason reason) {

  public SessionEnd {
    Objects.requireNonNull(userId, "userId");
    Objects.requireNonNull(sessionId, "sessionId");
    Objects.requireNonNull(reason, "reason");
    if (userId.isBlank() || sessionId.isBlank()) {
      throw new IllegalArgumentException("userId 와 sessionId 는 비어 있을 수 없습니다.");
    }
  }

  @Override
  public String toString() {
    return "SessionEnd[userId=" + userId + ", sessionId=***, reason=" + reason + "]";
  }
}
