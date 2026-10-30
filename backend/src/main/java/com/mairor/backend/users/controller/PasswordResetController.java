package com.mairor.backend.users.controller;

import com.mairor.backend.users.dto.request.PasswordResetPasswordRequest;
import com.mairor.backend.users.dto.request.PasswordResetRequest;
import com.mairor.backend.users.dto.request.PasswordResetVerificationRequest;
import com.mairor.backend.users.dto.response.PasswordResetSentResponse;
import com.mairor.backend.users.dto.response.PasswordResetVerifiedResponse;
import com.mairor.backend.users.service.PasswordResetService;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.users.support.CurrentSessionEnder;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 비밀번호 재설정 API (API-USERS-008 인증번호 발송, API-USERS-009 인증번호 확인, API-USERS-010 새 비밀번호 저장). 비회원이 호출하므로
 * {@link com.mairor.backend.common.security.SecurityConfig}에서 열고 허용 Origin 검증으로 보호한다.
 */
@Tag(
    name = "비밀번호 재설정",
    description =
        "이메일로 받은 인증번호로 비밀번호를 다시 정한다. 인증번호 발송 → 인증번호 확인 → 새 비밀번호 저장 순서다."
            + " 로그인 없이 호출하고 허용된 Origin 에서 보낸 요청만 받는다.")
@RestController
@RequestMapping("/v1/users/password-reset")
public class PasswordResetController {

  private final PasswordResetService passwordResetService;

  public PasswordResetController(PasswordResetService passwordResetService) {
    this.passwordResetService = passwordResetService;
  }

  @Operation(
      summary = "재설정 인증번호 발송",
      description =
          """
          가입한 이메일로 비밀번호 재설정 인증번호를 보낸다.

          - 가입 여부와 상관없이 같은 응답이다. 가입하지 않은 이메일에는 메일을 보내지 않고, Google 로그인 전용 계정에는 인증번호 대신 Google 로 로그인하라는 안내를 보낸다.
          - 같은 이메일은 재발송 간격과 시간당 횟수 제한이 있다. 다시 보내면 이전 인증번호는 무효가 된다.
          - 같은 이메일의 다른 재설정 요청이 처리 중이면 429 와 `Retry-After` 로 거절한다.
          """)
  @ApiResponse(
      responseCode = "202",
      description =
          "요청을 받았다. `expiresInSeconds` 안에 인증하고, `resendAvailableInSeconds` 뒤에 다시 보낼 수 있다.")
  @ApiResponse(responseCode = "400", description = "이메일 형식이 올바르지 않다. (VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "429",
      description =
          "재발송 간격 안이거나 횟수를 넘었다(USERS_RESET_RATE_LIMITED), 또는 같은 이메일의 요청이 처리 중이다(TOO_MANY_REQUESTS)."
              + " `Retry-After` 초 뒤에 다시 시도한다.")
  @ApiResponse(
      responseCode = "503",
      description = "메일 발송에 실패했다. 잠시 뒤 다시 시도한다. (USERS_RESET_SEND_FAILED)")
  @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.ACCEPTED)
  public PasswordResetSentResponse send(
      @Valid @RequestBody PasswordResetRequest request, HttpServletRequest http) {
    return passwordResetService.send(request, http.getRemoteAddr());
  }

  @Operation(
      summary = "재설정 인증번호 확인",
      description =
          """
          메일로 받은 인증번호를 확인하고 새 비밀번호 저장에 쓸 `resetToken` 을 받는다.

          - 토큰은 `expiresAt` 까지 쓸 수 있고 비밀번호 변경과 세션 정리가 끝나면 폐기된다. 그 전에 규칙 위반이나 세션 정리 실패로 끝났으면 다시 쓸 수 있고, 같은 이메일로 다시 인증하면 이전 토큰은 무효가 된다.
          - 여러 번 틀리면 막히므로 인증번호를 다시 받는다.
          - 같은 이메일의 다른 재설정 요청이 처리 중이면 429 와 `Retry-After` 로 거절한다.
          """)
  @ApiResponse(responseCode = "200", description = "인증됐다.")
  @ApiResponse(
      responseCode = "400",
      description = "인증번호가 맞지 않거나 형식이 올바르지 않다. (USERS_RESET_CODE_INVALID, VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "410",
      description = "인증번호가 만료됐거나 요청 기록이 없다. 다시 받는다. (USERS_RESET_CODE_EXPIRED)")
  @ApiResponse(
      responseCode = "429",
      description =
          "너무 많이 틀렸다(USERS_RESET_CODE_ATTEMPTS_EXCEEDED, 인증번호를 다시 받는다), 또는 같은 이메일의 요청이 처리 중이다(TOO_MANY_REQUESTS).")
  @PostMapping(path = "/verification", consumes = MediaType.APPLICATION_JSON_VALUE)
  public PasswordResetVerifiedResponse verify(
      @Valid @RequestBody PasswordResetVerificationRequest request) {
    return passwordResetService.verify(request);
  }

  @Operation(
      summary = "새 비밀번호 저장",
      description =
          """
          인증번호 확인에서 받은 `resetToken` 으로 새 비밀번호를 저장하고 이 계정의 모든 기기를 로그아웃시킨다.

          - 자동 로그인하지 않는다. 새 비밀번호로 다시 로그인한다. 같은 계정으로 로그인한 기기에서 보내면 그 기기도 로그아웃되고 만료 쿠키가 내려간다.
          - 규칙 위반으로 400 이면 토큰은 그대로라 고쳐서 다시 보낸다. 500·503 이면 비밀번호는 이미 바뀌었을 수 있으니 같은 요청을 다시 보내 마무리한다.
          - 같은 이메일의 다른 재설정 요청이 처리 중이면 429 와 `Retry-After` 로 거절한다.
          """)
  @ApiResponse(responseCode = "204", description = "새 비밀번호를 저장했고 모든 기기를 로그아웃시켰다.")
  @ApiResponse(
      responseCode = "400",
      description = "새 비밀번호가 규칙에 맞지 않거나, 확인값과 다르거나, 현재 비밀번호와 같다. 토큰은 그대로다. (VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "410",
      description = "토큰이 만료됐거나, 이미 썼거나, 새로 인증해서 바뀌었다. 인증번호를 다시 받는다. (USERS_RESET_TOKEN_EXPIRED)")
  @ApiResponse(
      responseCode = "429",
      description = "같은 이메일의 다른 재설정 요청이 처리 중이다. `Retry-After` 초 뒤에 다시 시도한다. (TOO_MANY_REQUESTS)")
  @ApiResponse(
      responseCode = "500",
      description = "비밀번호는 바꿨지만 일부 기기를 로그아웃시키지 못했다. 같은 요청을 다시 보낸다. (INTERNAL_ERROR)")
  @ApiResponse(
      responseCode = "503",
      description = "저장소에 일시적으로 접근하지 못했다. 같은 요청을 다시 보낸다. (SERVICE_UNAVAILABLE)")
  @PutMapping(path = "/password", consumes = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void resetPassword(
      @Valid @RequestBody PasswordResetPasswordRequest request,
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest http) {
    HttpSession current = http.getSession(false);
    boolean endedCurrentSession =
        passwordResetService.resetPassword(
            request,
            principal == null ? null : principal.userId(),
            current == null ? null : current.getId());
    if (endedCurrentSession) {
      // 저장소에서 지운 현재 세션이 응답 커밋 때 다시 저장되지 않게 이 요청의 세션도 끝낸다
      CurrentSessionEnder.end(http);
    }
  }
}
