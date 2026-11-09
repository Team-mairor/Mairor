package com.mairor.backend.users.controller;

import com.mairor.backend.common.error.ErrorResponse;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.http.MediaType;

/**
 * 로그인·기기 관리 API 문서의 요청·응답 예시. 애너테이션 값으로 쓰려고 상수로 둔다. 여러 API 에 같은 모양으로 붙는 응답(401·CSRF 403·404)은 메타
 * 애너테이션으로 묶었다. 401 메타 애너테이션({@link Unauthorized})은 다른 도메인의 로그인 필요 API 도 쓴다.
 */
public final class AuthApiDocs {

  private AuthApiDocs() {}

  /** 세션 쿠키가 없거나 만료된 요청의 401. */
  @Retention(RetentionPolicy.RUNTIME)
  @Target(ElementType.METHOD)
  @ApiResponse(
      responseCode = "401",
      description = "로그인이 필요하다. 세션 쿠키가 없거나, 3일 동안 요청이 없었거나, 로그인한 지 30일이 지났다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples = @ExampleObject(name = "UNAUTHORIZED", value = AuthApiDocs.UNAUTHORIZED)))
  public @interface Unauthorized {}

  /** 변경 요청의 CSRF 토큰 거절 403. 세션이 없는 변경 요청도 인가보다 CSRF 검사가 먼저라 이 응답이 된다. */
  @Retention(RetentionPolicy.RUNTIME)
  @Target(ElementType.METHOD)
  @ApiResponse(
      responseCode = "403",
      description =
          "X-CSRF-TOKEN 이 없거나 틀리다. 세션 없이 보낸 변경 요청도 같은 응답이다."
              + " GET /v1/users/me 로 토큰을 다시 받아 한 번만 재시도하고, 그 호출이 401 이면 이미 로그아웃된 상태다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples = @ExampleObject(name = "CSRF_INVALID", value = AuthApiDocs.CSRF_INVALID)))
  @interface CsrfRejected {}

  /** 없는 값·이미 끝난 기기·다른 회원의 기기를 구분하지 않는 404. */
  @Retention(RetentionPolicy.RUNTIME)
  @Target(ElementType.METHOD)
  @ApiResponse(
      responseCode = "404",
      description = "이 회원의 유효한 기기 중에 해당 sessionRef 가 없다(없는 값·형식 오류·이미 끝난 기기·다른 회원의 값을 구분하지 않는다).",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples = @ExampleObject(name = "NOT_FOUND", value = AuthApiDocs.NOT_FOUND)))
  @interface DeviceNotFound {}

  /** 없는 리소스와 다른 회원 소유 리소스를 구분하지 않는 공통 404. */
  @Retention(RetentionPolicy.RUNTIME)
  @Target(ElementType.METHOD)
  @ApiResponse(
      responseCode = "404",
      description = "요청한 리소스를 찾을 수 없다. (NOT_FOUND)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class),
              examples = @ExampleObject(name = "NOT_FOUND", value = AuthApiDocs.NOT_FOUND)))
  public @interface NotFound {}

  static final String LOGIN_REQUEST =
      """
      {"email": "user@example.com", "password": "Password1!"}""";

  static final String USER_AND_TOKEN =
      """
      {
        "user": {
          "userId": "3f2b8c1e-5a7d-4e6f-9b0a-1c2d3e4f5a6b",
          "email": "user@example.com",
          "nickname": null,
          "provider": "LOCAL",
          "createdAt": "2026-10-29T03:00:00Z"
        },
        "csrfToken": "YqfRQxgFY0ZD43De9XhCs06V1s7tLnezDQXnS6jao1qX36DNU5Czdis1VH9u10fvkFV2gSil-6-PHxKeazfXesrqx2uu7JH9"
      }""";

  static final String SESSION_LIST =
      """
      {
        "items": [
          {
            "sessionRef": "9d1c3b7a-2e4f-4a6b-8c0d-1e2f3a4b5c6d",
            "device": "Chrome · Windows",
            "createdAt": "2026-10-29T03:00:00Z",
            "lastAccessedAt": "2026-10-29T05:30:00Z",
            "current": true
          },
          {
            "sessionRef": "5a7b9c1d-3e5f-4071-9283-a4b5c6d7e8f9",
            "device": "Safari · iOS",
            "createdAt": "2026-10-27T09:10:00Z",
            "lastAccessedAt": "2026-10-28T20:00:00Z",
            "current": false
          }
        ]
      }""";

  static final String VALIDATION_FAILED =
      """
      {"code": "VALIDATION_FAILED", "message": "입력값이 올바르지 않습니다.",
       "details": [{"field": "email", "reason": "필수 값입니다."}]}""";

  static final String INVALID_CREDENTIALS =
      """
      {"code": "USERS_INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호를 확인해 주세요."}""";

  static final String FORBIDDEN_ORIGIN =
      """
      {"code": "FORBIDDEN", "message": "요청 권한이 없습니다."}""";

  static final String UNSUPPORTED_MEDIA_TYPE =
      """
      {"code": "UNSUPPORTED_MEDIA_TYPE", "message": "Unsupported Media Type"}""";

  static final String LOGIN_RATE_LIMITED =
      """
      {"code": "USERS_LOGIN_RATE_LIMITED", "message": "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요."}""";

  static final String TOO_MANY_REQUESTS =
      """
      {"code": "TOO_MANY_REQUESTS", "message": "요청 한도를 초과했습니다."}""";

  static final String UNAUTHORIZED =
      """
      {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}""";

  static final String CSRF_INVALID =
      """
      {"code": "CSRF_INVALID", "message": "요청 보안 토큰이 유효하지 않습니다."}""";

  static final String NOT_FOUND =
      """
      {"code": "NOT_FOUND", "message": "요청한 리소스를 찾을 수 없습니다."}""";

  static final String SET_COOKIE_ISSUED =
      "세션 쿠키 __Host-sessionId (HttpOnly, Secure, SameSite=Strict, Path=/, Max-Age=259200). 로그인할 때마다 새 세션 ID 로 발급된다.";

  static final String SET_COOKIE_REFRESHED =
      "같은 세션 ID 의 쿠키가 다시 내려와 보관 기간이 늘어난다(Max-Age 는 3일, 로그인 후 30일까지 남은 시간이 더 짧으면 그 값).";

  static final String SET_COOKIE_EXPIRED = "세션 쿠키를 지우는 만료 쿠키(Max-Age=0).";

  static final String RETRY_AFTER = "다시 시도할 수 있기까지 남은 시간(초).";
}
