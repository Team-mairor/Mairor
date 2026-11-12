package com.mairor.backend.users.controller;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.users.dto.request.GoogleSignUpRequest;
import com.mairor.backend.users.dto.response.GoogleSignupPendingResponse;
import com.mairor.backend.users.dto.response.LoginResponse;
import com.mairor.backend.users.service.GoogleLoginService;
import com.mairor.backend.users.service.GoogleSignUpService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Google 로그인 API (API-USERS-006 시작, API-USERS-007 callback, 가입 대기 조회, 가입 완료). 비회원이 호출하므로 {@link
 * com.mairor.backend.common.security.SecurityConfig}에서 연다. 가입 완료(POST)는 허용 Origin 검증으로 보호한다. 응답은 모두
 * {@code Cache-Control: no-store} 다.
 */
@Tag(
    name = "Google 로그인",
    description =
        "Google 계정으로 로그인한다. 로그인 시작은 fetch 가 아니라 화면 이동이고, Google 을 거쳐 서비스 화면으로 돌아온다."
            + " 처음 온 사용자는 추가 정보 화면에서 약관에 동의해야 회원이 된다.")
@RestController
@RequestMapping("/v1/users/oauth/google")
public class GoogleLoginController {

  private final GoogleLoginService googleLoginService;
  private final GoogleSignUpService googleSignUpService;

  public GoogleLoginController(
      GoogleLoginService googleLoginService, GoogleSignUpService googleSignUpService) {
    this.googleLoginService = googleLoginService;
    this.googleSignUpService = googleSignUpService;
  }

  @Operation(
      summary = "Google 로그인 시작",
      description =
          """
          Google 인증 화면으로 보낸다(302). 이 주소로 화면을 이동시킨다.

          - 로그인 시작만으로는 회원·세션을 만들지 않는다. 인증 결과는 callback 이 처리한다.
          - 인증을 마치기까지의 시간이 정해져 있다. 지나면 다시 시작한다.
          """)
  @ApiResponse(
      responseCode = "302",
      description =
          "Google 인증 화면으로 이동한다. 시도 제한 또는 Google 인증 불가 시 각각 `/login?error=USERS_LOGIN_RATE_LIMITED`, `/login?error=USERS_GOOGLE_AUTH_UNAVAILABLE`로 이동한다.")
  @GetMapping
  public ResponseEntity<Void> start(HttpServletRequest request) {
    try {
      GoogleLoginService.Start start = googleLoginService.start(request);
      return ResponseEntity.status(302)
          .location(URI.create(start.authorizationUri()))
          .header(HttpHeaders.SET_COOKIE, start.cookie().toString())
          .cacheControl(CacheControl.noStore())
          .build();
    } catch (BusinessException e) {
      if (!"USERS_LOGIN_RATE_LIMITED".equals(e.code())
          && !"USERS_GOOGLE_AUTH_UNAVAILABLE".equals(e.code())) {
        throw e;
      }
      ResponseEntity.BodyBuilder redirect =
          ResponseEntity.status(HttpStatus.FOUND)
              .location(URI.create("/login?error=" + e.code()))
              .cacheControl(CacheControl.noStore());
      if (e.retryAfterSeconds() != null) {
        redirect.header(HttpHeaders.RETRY_AFTER, String.valueOf(e.retryAfterSeconds()));
      }
      return redirect.build();
    }
  }

  @Operation(
      summary = "Google 로그인 복귀",
      description =
          """
          Google 인증을 마치고 돌아온 요청을 처리해 서비스 화면으로 보낸다(302). Google 이 호출하는 주소라 직접 부르지 않는다.

          - 연결된 Google 회원이면 로그인 세션을 만들고 메인(`/`)으로 보낸다. 메인에서 내 계정 조회로 회원 정보와 CSRF 토큰을 받는다.
          - 처음 온 사용자는 회원·세션을 만들지 않고 가입 대기를 저장해 추가 정보 화면(`/signup/google`)으로 보낸다. 같은 이메일의 계정은 자동으로 연결하지 않는다.
          - 실패하면 로그인 화면(`/login?error=<코드>`)으로 보낸다. 코드: USERS_GOOGLE_AUTH_CANCELLED(취소), USERS_GOOGLE_AUTH_FAILED(검증 실패), USERS_OAUTH_STATE_INVALID(시작 기록 없음·만료·재사용), USERS_ACCOUNT_LINK_REQUIRED(같은 이메일의 계정이 있음), USERS_GOOGLE_AUTH_UNAVAILABLE(일시 장애).
          """)
  @ApiResponse(responseCode = "302", description = "메인, 추가 정보 화면 또는 로그인 화면으로 이동한다.")
  @GetMapping("/callback")
  public ResponseEntity<Void> callback(
      @CookieValue(name = GoogleLoginService.AUTHORIZATION_COOKIE, required = false) String key,
      @RequestParam(required = false) String state,
      @RequestParam(required = false) String code,
      @RequestParam(required = false) String error,
      HttpServletRequest request,
      HttpServletResponse response) {
    GoogleLoginService.Callback result =
        googleLoginService.callback(key, state, code, error, request, response);
    ResponseEntity.BodyBuilder redirect =
        ResponseEntity.status(302)
            .location(URI.create(result.location()))
            .header(
                HttpHeaders.SET_COOKIE, GoogleLoginService.expiredAuthorizationCookie().toString())
            .cacheControl(CacheControl.noStore());
    if (result.signupCookie() != null) {
      redirect.header(HttpHeaders.SET_COOKIE, result.signupCookie().toString());
    }
    return redirect.build();
  }

  @Operation(
      summary = "Google 가입 대기 조회",
      description =
          """
          Google 로 처음 온 사용자의 가입 대기를 조회한다. 추가 정보 화면이 이메일·이름을 보여 주는 데 쓴다.

          - callback 이 준 가입 대기 쿠키로 찾는다. 조회해도 가입 대기는 남는다.
          - 가입 대기에는 유효 시간이 있다. 지나면 Google 로그인부터 다시 시작한다.
          """)
  @ApiResponse(responseCode = "200", description = "가입 대기가 있다.")
  @ApiResponse(
      responseCode = "410",
      description = "가입 대기가 없거나 만료됐다. Google 로 다시 시작한다. (USERS_GOOGLE_SIGNUP_EXPIRED)")
  @GetMapping("/signup")
  public ResponseEntity<GoogleSignupPendingResponse> pendingSignup(
      @CookieValue(name = GoogleLoginService.SIGNUP_COOKIE, required = false) String key) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(googleLoginService.pendingSignup(key));
  }

  @Operation(
      summary = "Google 가입 완료",
      description =
          """
          약관 동의와 추가 정보를 받아 Google 계정으로 회원을 만들고 바로 로그인시킨다. 세션 쿠키가 내려오고, 응답의 `csrfToken` 은 변경 요청의 `X-CSRF-TOKEN` 헤더에 넣는다.

          - 이메일 가입에서 이메일·비밀번호·인증 토큰을 뺀 입력이고 규칙과 오류 형식이 같다. 비밀번호는 없다.
          - 입력 오류(400)는 가입 대기를 쓰지 않으므로 고쳐 다시 보낸다. 그 밖의 응답이 나오면 가입 대기는 사라진다.
          - 같은 이메일의 계정이 그사이 생겼으면 자동으로 연결하지 않는다.
          """)
  @ApiResponse(responseCode = "201", description = "가입하고 로그인했다.")
  @ApiResponse(
      responseCode = "400",
      description =
          "입력값이 올바르지 않거나(VALIDATION_FAILED) 필수 약관에 동의하지 않았다(USERS_REQUIRED_AGREEMENT_MISSING).")
  @ApiResponse(responseCode = "403", description = "허용되지 않은 Origin 이다. (FORBIDDEN)")
  @ApiResponse(
      responseCode = "409",
      description = "같은 이메일로 가입된 계정이 있다. 이메일 로그인을 안내한다. (USERS_ACCOUNT_LINK_REQUIRED)")
  @ApiResponse(
      responseCode = "410",
      description = "가입 대기가 없거나 만료·이미 사용됐다. Google 로 다시 시작한다. (USERS_GOOGLE_SIGNUP_EXPIRED)")
  @PostMapping(path = "/signup", consumes = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<LoginResponse> signUp(
      @CookieValue(name = GoogleLoginService.SIGNUP_COOKIE, required = false) String key,
      @Valid @RequestBody GoogleSignUpRequest request,
      HttpServletRequest httpRequest,
      HttpServletResponse httpResponse) {
    LoginResponse body = googleSignUpService.signUp(key, request, httpRequest, httpResponse);
    return ResponseEntity.status(HttpStatus.CREATED)
        .header(HttpHeaders.SET_COOKIE, GoogleLoginService.expiredSignupCookie().toString())
        .cacheControl(CacheControl.noStore())
        .body(body);
  }
}
