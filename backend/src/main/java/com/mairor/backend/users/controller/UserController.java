package com.mairor.backend.users.controller;

import com.mairor.backend.users.dto.request.EmailAvailabilityRequest;
import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.response.EmailAvailabilityResponse;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.service.EmailAvailabilityService;
import com.mairor.backend.users.service.UserSignUpService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
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
 * 회원 API: 자체 회원가입(API-USERS-001), 가입 가능 이메일 확인(API-USERS-011). 비회원이 호출하며 가입은 로그인(세션·토큰 발급)을 하지 않는다.
 */
@Tag(
    name = "회원가입",
    description =
        "가입 가능한 이메일 확인과 자체 회원가입. 로그인 없이 호출하고 허용된 Origin 에서 보낸 요청만 받는다."
            + " 가입은 로그인(세션·토큰 발급)을 하지 않는다.")
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
  @Operation(
      summary = "가입 가능 이메일 확인",
      description =
          """
          이메일이 가입에 쓸 수 있는지 확인한다.

          - 이메일은 URL 에 남지 않도록 본문으로 보낸다.
          - IP 당 요청 횟수를 제한한다.
          """)
  @ApiResponse(responseCode = "200", description = "확인 결과. `available` 이 true 면 가입할 수 있다.")
  @ApiResponse(responseCode = "400", description = "이메일 형식이 올바르지 않다. (VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "429",
      description = "요청이 너무 많다. `Retry-After` 초 뒤에 다시 시도한다. (USERS_EMAIL_CHECK_RATE_LIMITED)")
  @PostMapping(path = "/email-availability", consumes = MediaType.APPLICATION_JSON_VALUE)
  public EmailAvailabilityResponse checkEmailAvailability(
      @Valid @RequestBody EmailAvailabilityRequest request, HttpServletRequest http) {
    return emailAvailabilityService.check(request, http.getRemoteAddr());
  }

  @Operation(
      summary = "회원가입",
      description =
          """
          이메일·비밀번호로 가입한다. 가입만 하고 로그인은 하지 않으므로 이어서 로그인을 호출한다.

          - 필수 약관(TERMS, PRIVACY, AGE_OVER_14)에 모두 동의해야 한다.
          - 이메일 인증을 요구하는 환경에서는 인증 확인 응답의 `verificationToken` 을           `emailVerificationToken` 에 넣는다.
          """)
  @ApiResponse(responseCode = "201", description = "가입했다.")
  @ApiResponse(
      responseCode = "400",
      description = "입력이 올바르지 않거나 이메일 인증이 필요하다. (VALIDATION_FAILED, USERS_EMAIL_NOT_VERIFIED)")
  @ApiResponse(responseCode = "409", description = "이미 가입된 이메일이다. (USERS_EMAIL_DUPLICATE)")
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
