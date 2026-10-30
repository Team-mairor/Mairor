package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.EmailNormalizer;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/** 비밀번호 재설정 인증번호 확인 요청 (API-USERS-009). {@code code}는 6자리 숫자 문자열이다. */
public record PasswordResetVerificationRequest(
    @Schema(description = "인증번호를 받은 이메일", example = "user@example.com")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 254, message = "254자 이하여야 합니다.")
        @Email(regexp = ".+@.+\\..+", message = "올바른 이메일 형식이 아닙니다.")
        String email,
    @Schema(description = "메일로 받은 6자리 인증번호", example = "123456")
        @NotNull(message = "필수 값입니다.")
        @Pattern(regexp = "\\d{6}", message = "6자리 숫자여야 합니다.")
        String code) {

  public PasswordResetVerificationRequest {
    email = EmailNormalizer.normalize(email);
  }

  /** 이메일과 인증번호가 로그에 남지 않도록 가린다. */
  @Override
  public String toString() {
    return "PasswordResetVerificationRequest[email=***, code=***]";
  }
}
