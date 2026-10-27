package com.mairor.backend.users.controller;

import com.mairor.backend.users.dto.request.SignUpRequest;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.service.UserSignUpService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회원 API. 지금은 자체 회원가입(API-USERS-001)만 있다.
 *
 * <p>비회원이 호출하므로 {@link com.mairor.backend.common.security.SecurityConfig}에서 이 경로만 열고 CSRF 토큰 대신 허용
 * Origin 검증으로 보호한다. 가입은 계정만 만들고 로그인(세션·토큰 발급)은 하지 않는다.
 */
@RestController
@RequestMapping("/v1/users")
public class UserController {

  private final UserSignUpService userSignUpService;

  public UserController(UserSignUpService userSignUpService) {
    this.userSignUpService = userSignUpService;
  }

  @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.CREATED)
  public UserResponse signUp(@Valid @RequestBody SignUpRequest request) {
    return userSignUpService.signUp(request);
  }
}
