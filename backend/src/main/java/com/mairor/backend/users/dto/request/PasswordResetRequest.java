package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 비밀번호 재설정 인증번호 발송 요청 (API-USERS-008). */
public record PasswordResetRequest(
    @Schema(description = "가입할 때 쓴 이메일", example = "user@example.com")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        @Email(regexp = ".+@.+\\..+", message = "올바른 이메일 형식이 아닙니다.")
        String email) {

  public PasswordResetRequest {
    email = EmailNormalizer.normalize(email);
  }

  /** 이메일이 로그에 남지 않도록 가린다. */
  @Override
  public String toString() {
    return "PasswordResetRequest[email=***]";
  }
}
