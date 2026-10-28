package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 가입 이메일 인증번호 발송 요청 (API-USERS-012). 이메일은 가입과 같은 규칙으로 정규화한 뒤 검증한다. */
public record EmailVerificationRequest(
    @Schema(description = "인증번호를 받을 이메일", example = "user@example.com")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        @Email(regexp = ".+@.+\\..+", message = "올바른 이메일 형식이 아닙니다.")
        String email) {

  public EmailVerificationRequest {
    email = EmailNormalizer.normalize(email);
  }

  @Override
  public String toString() {
    return "EmailVerificationRequest[email=***]";
  }
}
