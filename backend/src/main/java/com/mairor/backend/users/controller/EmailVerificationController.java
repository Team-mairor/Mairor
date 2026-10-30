package com.mairor.backend.users.controller;

import com.mairor.backend.users.dto.request.EmailVerificationConfirmRequest;
import com.mairor.backend.users.dto.request.EmailVerificationRequest;
import com.mairor.backend.users.dto.response.EmailVerificationSentResponse;
import com.mairor.backend.users.dto.response.EmailVerifiedResponse;
import com.mairor.backend.users.service.EmailVerificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 가입 이메일 소유 확인 API (API-USERS-012 발송, API-USERS-013 확인). 비회원이 호출하므로 {@link
 * com.mairor.backend.common.security.SecurityConfig}에서 열고 허용 Origin 검증으로 보호한다. 가입에 인증을 요구하는지와 상관없이
 * 열려 있다.
 */
@Tag(
    name = "이메일 인증",
    description =
        "가입 이메일의 소유 확인. 인증번호를 메일로 보내고(발송) 입력한 번호를 확인한다."
            + " 가입에 인증을 요구하도록 설정했을 때 확인 응답의 토큰을 가입 요청에 실어야 한다."
            + " 로그인 없이 호출하고 허용된 Origin 에서 보낸 요청만 받는다.")
@RestController
@RequestMapping("/v1/users/email-verification")
public class EmailVerificationController {

  private final EmailVerificationService emailVerificationService;

  public EmailVerificationController(EmailVerificationService emailVerificationService) {
    this.emailVerificationService = emailVerificationService;
  }

  @Operation(
      summary = "인증번호 발송",
      description =
          """
          가입할 이메일로 6자리 인증번호를 보낸다.

          - 같은 이메일은 쿨다운과 시간당 횟수 제한이 있다. 응답의 `resendAvailableInSeconds` 뒤에 다시 보낸다.
          - 이미 가입된 이메일에는 보내지 않는다.
          """)
  @ApiResponse(responseCode = "202", description = "메일을 보냈다. `expiresInSeconds` 안에 인증한다.")
  @ApiResponse(responseCode = "400", description = "이메일 형식이 올바르지 않다. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "409", description = "이미 가입된 이메일이다. (USERS_EMAIL_DUPLICATE)")
  @ApiResponse(
      responseCode = "429",
      description =
          "재발송 쿨다운 중이거나 횟수를 넘었다. `Retry-After` 초 뒤에 다시 시도한다. (USERS_EMAIL_SEND_RATE_LIMITED)")
  @ApiResponse(
      responseCode = "503",
      description = "메일 발송에 실패했다. 잠시 뒤 다시 시도한다. (USERS_EMAIL_SEND_FAILED)")
  @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.ACCEPTED)
  public EmailVerificationSentResponse send(
      @Valid @RequestBody EmailVerificationRequest request, HttpServletRequest http) {
    return emailVerificationService.send(request, http.getRemoteAddr());
  }

  @Operation(
      summary = "인증번호 확인",
      description =
          """
          메일로 받은 인증번호를 확인하고 가입에 쓸 `verificationToken` 을 받는다.

          - 토큰은 `expiresAt` 까지 유효하며 회원가입의 `emailVerificationToken` 에 넣는다.
          - 여러 번 틀리면 막히므로 인증번호를 다시 받는다.
          """)
  @ApiResponse(responseCode = "200", description = "인증됐다.")
  @ApiResponse(
      responseCode = "400",
      description = "인증번호가 맞지 않거나 형식이 올바르지 않다. (USERS_EMAIL_CODE_INVALID, VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "410",
      description = "인증번호가 만료됐거나 요청 기록이 없다. 다시 받는다. (USERS_EMAIL_CODE_EXPIRED)")
  @ApiResponse(
      responseCode = "429",
      description = "너무 많이 틀렸다. 인증번호를 다시 받는다. (USERS_EMAIL_CODE_ATTEMPTS_EXCEEDED)")
  @PostMapping(path = "/verification", consumes = MediaType.APPLICATION_JSON_VALUE)
  public EmailVerifiedResponse confirm(
      @Valid @RequestBody EmailVerificationConfirmRequest request) {
    return emailVerificationService.confirm(request);
  }
}
