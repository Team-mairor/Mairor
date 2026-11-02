package com.mairor.backend.users.support;

import com.mairor.backend.common.error.BusinessException;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.registration.ClientRegistration;

/**
 * Google 클라이언트 등록 정보. 설정이 없는 환경(키 없는 로컬 등)에서는 비어 있고, 꺼내면 503 {@code USERS_GOOGLE_AUTH_UNAVAILABLE}
 * 이다. 테스트는 token·JWKS 주소를 가짜 서버로 바꾼 등록 정보로 이 빈을 바꿔 끼운다.
 */
public class GoogleClientRegistrations {

  private final ClientRegistration registration;

  /**
   * @param registration Google 등록 정보. 설정이 없으면 {@code null}
   */
  public GoogleClientRegistrations(ClientRegistration registration) {
    this.registration = registration;
  }

  public boolean available() {
    return registration != null;
  }

  /** 등록 정보를 돌려준다. 없으면 503 {@code USERS_GOOGLE_AUTH_UNAVAILABLE}. */
  public ClientRegistration require() {
    if (registration == null) {
      throw unavailable();
    }
    return registration;
  }

  public static BusinessException unavailable() {
    return new BusinessException(
        HttpStatus.SERVICE_UNAVAILABLE,
        GoogleAuthFailure.UNAVAILABLE.code(),
        "지금은 Google 로그인을 쓸 수 없습니다. 잠시 후 다시 시도하거나 이메일로 로그인해 주세요.");
  }
}
