package com.mairor.backend.users.support;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;
import org.springframework.security.core.AuthenticatedPrincipal;

/**
 * 로그인한 회원의 세션 principal. 세션 저장소가 JDK 직렬화로 저장하므로 UUID·문자열만 가진다. 엔티티나 비밀번호 해시는 담지 않는다.
 *
 * <p>{@link #getName()} 은 userId 문자열이다. Spring Session 이 이 값을 {@code PRINCIPAL_NAME} 으로 색인해서, 회원의
 * 모든 세션을 찾아 지우는 기능(기기 관리·비밀번호 재설정)이 이 값에 의존한다. 이메일은 바뀔 수 있어 쓰지 않는다. {@code toString()} 에 기대지 않도록
 * {@link AuthenticatedPrincipal} 로 이름을 직접 정한다.
 */
public record AuthenticatedUser(UUID userId, String email)
    implements AuthenticatedPrincipal, Serializable {

  public AuthenticatedUser {
    Objects.requireNonNull(userId, "userId");
    Objects.requireNonNull(email, "email");
  }

  @Override
  public String getName() {
    return userId.toString();
  }

  /** 인증 객체가 로그로 찍혀도 이메일이 새지 않게 한다. */
  @Override
  public String toString() {
    return "AuthenticatedUser[userId=" + userId + "]";
  }
}
