package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 가입 가능 이메일 확인 요청 (API-USERS-011). 이메일은 가입과 같은 규칙으로 정규화한 뒤 검증한다.
 *
 * <p>이메일이 URL·접근 로그에 남지 않도록 본문으로 받는다. {@link #toString()}도 값을 가린다.
 */
public record EmailAvailabilityRequest(
    @Schema(description = "가입 가능한지 확인할 이메일", example = "user@example.com")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        @Email(regexp = ".+@.+\\..+", message = "올바른 이메일 형식이 아닙니다.")
        String email) {

  public EmailAvailabilityRequest {
    email = EmailNormalizer.normalize(email);
  }

  @Override
  public String toString() {
    return "EmailAvailabilityRequest[email=***]";
  }
}
