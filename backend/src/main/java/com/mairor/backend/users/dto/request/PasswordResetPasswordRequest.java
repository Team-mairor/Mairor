package com.mairor.backend.users.dto.request;

import com.mairor.backend.users.support.PasswordNormalizer;
import com.mairor.backend.users.support.StrongPassword;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * 새 비밀번호 저장 요청 (API-USERS-010). 새 비밀번호는 가입과 같은 규칙이다. 비밀번호는 원문 그대로 두고 비교·해시 직전에만 {@link
 * PasswordNormalizer}를 적용한다.
 */
public record PasswordResetPasswordRequest(
    @Schema(description = "인증번호 확인에서 받은 토큰", example = "q8m2Zf0bXc1yTn6vKpR4sW7hJdLa9eGu")
        @NotBlank(message = "필수 값입니다.")
        @Size(max = 256, message = "256자 이하여야 합니다.")
        String resetToken,
    @Schema(description = "8~64자, 영문자·숫자·특수문자 각 1개 이상", example = "NewPassword1!")
        @NotNull(message = "필수 값입니다.")
        @Size(min = 8, max = 64, message = "8자 이상 64자 이하여야 합니다.")
        @StrongPassword
        String newPassword,
    @Schema(description = "새 비밀번호와 같은 값", example = "NewPassword1!") @NotNull(message = "필수 값입니다.")
        String newPasswordConfirm) {

  /** 토큰과 비밀번호가 로그에 남지 않도록 가린다. */
  @Override
  public String toString() {
    return "PasswordResetPasswordRequest[resetToken=***, newPassword=***, newPasswordConfirm=***]";
  }
}
