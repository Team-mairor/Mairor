package com.mairor.backend.users.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.dto.request.LoginRequest;
import com.mairor.backend.users.dto.response.LoginResponse;
import com.mairor.backend.users.service.UserAccountService;
import com.mairor.backend.users.service.UserLoginService;
import com.mairor.backend.users.support.CurrentSessionEnder;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회원 인증 API: 로그인(API-USERS-002), 로그아웃(API-USERS-003), 내 계정 조회(API-USERS-004). 로그인은 공개 경로이고 나머지는 세션과
 * CSRF 토큰이 필요하다.
 *
 * <p>로그인과 내 계정 조회 응답은 {@code Cache-Control: no-store} 로 내려 CSRF 토큰이 캐시에 남지 않게 한다. 쿠키 발급·만료는 Spring
 * Session 이 한다.
 */
@Tag(
    name = "회원 인증",
    description =
        "로그인·로그아웃·내 계정 조회. 로그인하면 세션 쿠키(__Host-sessionId)가 내려오고, 변경 요청에는 응답의 csrfToken 을"
            + " X-CSRF-TOKEN 헤더로 보내야 한다.")
@RestController
@RequestMapping("/v1/users")
public class UserAuthController {

  private final UserLoginService userLoginService;
  private final UserAccountService userAccountService;

  public UserAuthController(
      UserLoginService userLoginService, UserAccountService userAccountService) {
    this.userLoginService = userLoginService;
    this.userAccountService = userAccountService;
  }

  /** 로그인 (API-USERS-002). 성공하면 세션 쿠키와, 이후 변경 요청에 쓸 {@code csrfToken} 을 준다. */
  @Operation(
      summary = "로그인",
      description =
          """
          이메일·비밀번호로 로그인한다. 세션 쿠키가 내려오고, 응답의 `csrfToken` 은 변경 요청의 `X-CSRF-TOKEN` 헤더에 넣는다.

          - 실패 원인(미가입·비밀번호 오류·Google 전용 계정)은 구분하지 않고 모두 401 이다.
          - 반복 실패하면 잠시 잠기고, 그동안은 비밀번호가 맞아도 429 다. `Retry-After` 초 뒤에 다시 시도한다.
          """)
  @io.swagger.v3.oas.annotations.parameters.RequestBody(
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              examples = @ExampleObject(name = "로그인", value = AuthApiDocs.LOGIN_REQUEST)))
  @ApiResponse(
      responseCode = "200",
      description = "로그인 성공",
      headers = @Header(name = "Set-Cookie", description = AuthApiDocs.SET_COOKIE_ISSUED),
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = LoginResponse.class),
              examples = @ExampleObject(name = "성공", value = AuthApiDocs.USER_AND_TOKEN)))
  @ApiResponse(
      responseCode = "400",
      description = "이메일·비밀번호가 비었거나 크기 상한(이메일 254자, 비밀번호 256자)을 넘었거나 JSON 이 깨졌다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "VALIDATION_FAILED",
                      value = AuthApiDocs.VALIDATION_FAILED)))
  @ApiResponse(
      responseCode = "401",
      description = "이메일 또는 비밀번호가 맞지 않다. 원인을 구분하지 않는다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "USERS_INVALID_CREDENTIALS",
                      value = AuthApiDocs.INVALID_CREDENTIALS)))
  @ApiResponse(
      responseCode = "403",
      description = "허용되지 않은 Origin 이다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples = @ExampleObject(name = "FORBIDDEN", value = AuthApiDocs.FORBIDDEN_ORIGIN)))
  @ApiResponse(
      responseCode = "415",
      description = "요청 본문이 JSON 이 아니다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples =
                  @ExampleObject(
                      name = "UNSUPPORTED_MEDIA_TYPE",
                      value = AuthApiDocs.UNSUPPORTED_MEDIA_TYPE)))
  @ApiResponse(
      responseCode = "429",
      description =
          "반복 시도로 이메일이 잠겼거나(USERS_LOGIN_RATE_LIMITED) 서버가 일시적으로 혼잡하다(TOO_MANY_REQUESTS)."
              + " Retry-After 의 초가 지난 뒤 다시 시도한다.",
      headers = @Header(name = "Retry-After", description = AuthApiDocs.RETRY_AFTER),
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples = {
                @ExampleObject(
                    name = "USERS_LOGIN_RATE_LIMITED",
                    value = AuthApiDocs.LOGIN_RATE_LIMITED),
                @ExampleObject(name = "TOO_MANY_REQUESTS", value = AuthApiDocs.TOO_MANY_REQUESTS)
              }))
  @PostMapping(path = "/login", consumes = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<LoginResponse> login(
      @Valid @RequestBody LoginRequest request,
      HttpServletRequest httpRequest,
      HttpServletResponse httpResponse) {
    return noStore(userLoginService.login(request, httpRequest, httpResponse));
  }

  /** 로그아웃 (API-USERS-003). 현재 기기의 세션만 폐기하고 만료 쿠키를 내려 준다. 다른 기기의 로그인은 유지된다. */
  @Operation(
      summary = "로그아웃",
      description =
          """
          현재 기기만 로그아웃하고 세션 쿠키를 지운다. 다른 기기의 로그인은 유지된다.

          - 오류 응답이면 로그아웃됐다고 단정하지 말고 `내 계정 조회` 로 상태를 확인한다.
          """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "204",
      description = "로그아웃됐다.",
      headers = @Header(name = "Set-Cookie", description = AuthApiDocs.SET_COOKIE_EXPIRED))
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @PostMapping("/logout")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void logout(HttpServletRequest request) {
    // TODO(GUIDE-011): 미완료 실행을 ABANDONED 로 바꾸고 사진 접근을 막는다. 세션 폐기 이전에 실행해야 한다
    CurrentSessionEnder.end(request);
  }

  /**
   * 내 계정 조회 (API-USERS-004). 앱을 다시 열었을 때 로그인 상태를 확인하고, CSRF 토큰을 다시 받는 경로다. 토큰은 교체하지 않고 현재 세션의 것을
   * 돌려준다. 인증된 요청이 성공하므로 세션 쿠키 보관 기간도 함께 연장된다.
   */
  @Operation(
      summary = "내 계정 조회",
      description =
          """
          로그인 상태를 확인하고 `csrfToken` 을 다시 받는다.

          - 앱을 다시 열 때와 CSRF 403 이 난 뒤에 호출한다.
          - 성공하면 세션 쿠키 보관 기간이 늘어나므로 주기적으로 호출할 필요는 없다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "로그인 상태다.",
      headers = @Header(name = "Set-Cookie", description = AuthApiDocs.SET_COOKIE_REFRESHED),
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = LoginResponse.class),
              examples = @ExampleObject(name = "성공", value = AuthApiDocs.USER_AND_TOKEN)))
  @AuthApiDocs.Unauthorized
  @GetMapping("/me")
  public ResponseEntity<LoginResponse> me(
      Authentication authentication, HttpServletRequest request) {
    CsrfToken csrfToken = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
    return noStore(
        new LoginResponse(userAccountService.current(authentication), csrfToken.getToken()));
  }

  private static ResponseEntity<LoginResponse> noStore(LoginResponse body) {
    return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(body);
  }
}
