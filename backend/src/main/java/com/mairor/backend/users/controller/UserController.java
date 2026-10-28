package com.mairor.backend.users.controller;

import com.mairor.backend.users.dto.request.EmailAvailabilityRequest;
import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.response.EmailAvailabilityResponse;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.service.EmailAvailabilityService;
import com.mairor.backend.users.service.UserSignUpService;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
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
 * 회원 API: 자체 회원가입(API-USERS-001), 가입 가능 이메일 확인(API-USERS-011). 비회원이 호출하며 가입은 로그인(세션·토큰 발급)을 하지 않는다.
 */
@RestController
@RequestMapping("/v1/users")
public class UserController {

  private final UserSignUpService userSignUpService;
  private final EmailAvailabilityService emailAvailabilityService;

  public UserController(
      UserSignUpService userSignUpService, EmailAvailabilityService emailAvailabilityService) {
    this.userSignUpService = userSignUpService;
    this.emailAvailabilityService = emailAvailabilityService;
  }

  /** 가입 가능 이메일 확인 (API-USERS-011). 요청 제한은 접속한 쪽의 IP 기준이다. */
  @PostMapping(path = "/email-availability", consumes = MediaType.APPLICATION_JSON_VALUE)
  public EmailAvailabilityResponse checkEmailAvailability(
      @Valid @RequestBody EmailAvailabilityRequest request, HttpServletRequest http) {
    return emailAvailabilityService.check(request, http.getRemoteAddr());
  }

  @io.swagger.v3.oas.annotations.parameters.RequestBody(
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              examples =
                  @ExampleObject(
                      name = "필수 약관 3개 동의 (이메일 인증 사용 시 emailVerificationToken 추가)",
                      value =
                          """
                          {
                            "email": "user@example.com",
                            "password": "password",
                            "passwordConfirm": "password",
                            "nickname": "mairor_nickname",
                            "name": "홍길동",
                            "phone": "01012345678",
                            "birthDate": "2000-01-01",
                            "gender": "FEMALE",
                            "agreements": [
                              {"type": "TERMS", "version": "2026-10-26", "agreed": true},
                              {"type": "PRIVACY", "version": "2026-10-26", "agreed": true},
                              {"type": "AGE_OVER_14", "version": "2026-10-26", "agreed": true},
                              {"type": "MARKETING", "version": "2026-10-26", "agreed": false}
                            ],
                            "emailVerificationToken": "이메일 인증 확인 응답의 verificationToken"
                          }
                          """)))
  @PostMapping(path = "/signup", consumes = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.CREATED)
  public UserResponse signUp(@Valid @RequestBody SignUpRequest request) {
    return userSignUpService.signUp(request);
  }
}
