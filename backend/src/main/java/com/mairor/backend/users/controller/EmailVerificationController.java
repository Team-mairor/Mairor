package com.mairor.backend.users.controller;

import com.mairor.backend.users.dto.request.EmailVerificationConfirmRequest;
import com.mairor.backend.users.dto.request.EmailVerificationRequest;
import com.mairor.backend.users.dto.response.EmailVerificationSentResponse;
import com.mairor.backend.users.dto.response.EmailVerifiedResponse;
import com.mairor.backend.users.service.EmailVerificationService;
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
@RestController
@RequestMapping("/v1/users/email-verification")
public class EmailVerificationController {

  private final EmailVerificationService emailVerificationService;

  public EmailVerificationController(EmailVerificationService emailVerificationService) {
    this.emailVerificationService = emailVerificationService;
  }

  @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.ACCEPTED)
  public EmailVerificationSentResponse send(
      @Valid @RequestBody EmailVerificationRequest request, HttpServletRequest http) {
    return emailVerificationService.send(request, http.getRemoteAddr());
  }

  @PostMapping(path = "/verification", consumes = MediaType.APPLICATION_JSON_VALUE)
  public EmailVerifiedResponse confirm(
      @Valid @RequestBody EmailVerificationConfirmRequest request) {
    return emailVerificationService.confirm(request);
  }
}
