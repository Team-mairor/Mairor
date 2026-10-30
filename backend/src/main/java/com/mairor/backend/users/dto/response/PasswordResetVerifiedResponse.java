package com.mairor.backend.users.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

/**
 * 비밀번호 재설정 인증번호 확인 응답 (API-USERS-009). {@code resetToken}은 이 응답에서만 평문으로 나가고, 서버에는 해시만 남는다. 새 비밀번호
 * 저장(API-USERS-010) 요청에 실어 보낸다.
 */
public record PasswordResetVerifiedResponse(
    @Schema(
            description = "새 비밀번호 저장에 쓰는 토큰. 비밀번호 변경이 끝나면 폐기된다",
            example = "q8m2Zf0bXc1yTn6vKpR4sW7hJdLa9eGu")
        String resetToken,
    @Schema(description = "토큰이 만료되는 시각(UTC)", example = "2026-10-27T08:10:00Z") Instant expiresAt) {

  /** 토큰이 로그에 남지 않도록 가린다. */
  @Override
  public String toString() {
    return "PasswordResetVerifiedResponse[resetToken=***, expiresAt=" + expiresAt + "]";
  }
}
