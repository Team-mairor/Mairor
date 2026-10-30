package com.mairor.backend.users.controller;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.dto.response.SessionListResponse;
import com.mairor.backend.users.service.UserSessionService;
import com.mairor.backend.users.support.AuthenticatedUser;
import com.mairor.backend.users.support.CurrentSessionEnder;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.headers.Header;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 로그인 기기 관리: 내 기기 목록, 기기 하나 로그아웃, 전체 로그아웃. 모두 로그인이 필요하고 변경 요청은 CSRF 토큰이 필요하다. 본인 세션만 다룬다.
 *
 * <p>현재 기기를 지우는 경우(자기 자신을 지정하거나 전체 로그아웃)에는 로그아웃과 같이 현재 세션을 끝내고 만료 쿠키를 내려 준다. 다른 기기만 지우면 현재 기기는 그대로
 * 유지되고 쿠키도 평소처럼 갱신된다.
 */
@Tag(
    name = "로그인 기기 관리",
    description =
        "내 로그인 기기 목록, 기기 하나 로그아웃, 전체 로그아웃. 본인 기기만 다루며, 기기는 sessionRef 로 가리킨다."
            + " sessionRef 는 로그인 때 만든 값이며 실제 세션 ID(쿠키 값)가 아니다.")
@RestController
@RequestMapping("/v1/users/me/sessions")
public class UserSessionController {

  private final UserSessionService userSessionService;

  public UserSessionController(UserSessionService userSessionService) {
    this.userSessionService = userSessionService;
  }

  /** 내 로그인 기기 목록. */
  @Operation(
      summary = "내 로그인 기기 목록",
      description =
          """
          로그인되어 있는 내 기기 목록을 최근 사용 순으로 준다.

          - 지금 요청을 보낸 기기는 `current` 가 true 다.
          - 기기 이름은 "브라우저 · OS" 요약이며 IP 는 주지 않는다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "내 기기 목록",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = SessionListResponse.class),
              examples = @ExampleObject(name = "두 기기", value = AuthApiDocs.SESSION_LIST)))
  @AuthApiDocs.Unauthorized
  @GetMapping
  public ResponseEntity<SessionListResponse> list(
      @AuthenticationPrincipal AuthenticatedUser principal, HttpServletRequest request) {
    HttpSession current = request.getSession(false);
    String currentId = current == null ? null : current.getId();
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(new SessionListResponse(userSessionService.list(principal.userId(), currentId)));
  }

  /** 기기 하나 로그아웃. 없는 값·이미 끝난 기기·다른 회원의 값은 구분하지 않고 모두 404 로 응답해 다른 회원의 기기가 있는지 알 수 없게 한다. */
  @Operation(
      summary = "기기 하나 로그아웃",
      description =
          """
          목록의 `sessionRef` 로 기기 하나를 로그아웃시킨다.

          - 다른 기기를 지정하면 현재 기기는 유지된다.
          - 자기 자신을 지정하면 로그아웃과 같다.
          """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "204",
      description =
          "기기를 로그아웃시켰다. 다른 기기를 지정했으면 현재 기기의 세션 쿠키가 평소처럼 갱신되어 내려오고,"
              + " 자기 자신을 지정했으면 만료 쿠키(Max-Age=0)가 내려온다.",
      headers = @Header(name = "Set-Cookie", description = AuthApiDocs.SET_COOKIE_REFRESHED))
  @ApiResponse(
      responseCode = "500",
      description = "세션을 정리하지 못해 그 기기를 로그아웃하지 못했다. 기기는 그대로이니 같은 요청을 다시 보낸다. (INTERNAL_ERROR)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.DeviceNotFound
  @DeleteMapping("/{sessionRef}")
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void revoke(
      @Parameter(description = "목록에서 받은 기기 식별자", example = "5a7b9c1d-3e5f-4071-9283-a4b5c6d7e8f9")
          @PathVariable
          String sessionRef,
      @AuthenticationPrincipal AuthenticatedUser principal,
      HttpServletRequest request) {
    Optional<UUID> ref = parse(sessionRef);
    HttpSession current = request.getSession(false);
    String currentId = current == null ? null : current.getId();
    // 세션을 지우기 전에 종료 훅이 호출된다(SessionEndHook). 훅이 실패하면 세션을 지우지 않고 예외가 난다
    Optional<String> revoked =
        ref.flatMap(value -> userSessionService.revoke(principal.userId(), value, currentId));
    if (revoked.isEmpty()) {
      throw new BusinessException(ErrorCode.NOT_FOUND);
    }
    if (current != null && current.getId().equals(revoked.get())) {
      CurrentSessionEnder.end(request);
    }
  }

  /** 전체 기기 로그아웃. 현재 기기도 함께 로그아웃된다. */
  @Operation(
      summary = "전체 기기 로그아웃",
      description =
          """
          내 모든 기기를 로그아웃시킨다. 현재 기기도 포함된다.

          - 요청 시점에 있던 세션만 끊는다. 같은 순간에 시작된 로그인은 막지 못한다.
          - 도중에 실패하면 일부 기기만 끊길 수 있다. 현재 기기는 마지막에 끊으므로 실패 시 로그인이 유지된 채 500 이 오고, 같은 요청을 다시 보내면 된다.
          """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "204",
      description = "모든 기기를 로그아웃시켰다.",
      headers = @Header(name = "Set-Cookie", description = AuthApiDocs.SET_COOKIE_EXPIRED))
  @ApiResponse(
      responseCode = "500",
      description = "일부 기기를 로그아웃시키지 못했다. 현재 기기는 유지된다. 같은 요청을 다시 보낸다. (INTERNAL_ERROR)")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @DeleteMapping
  @ResponseStatus(HttpStatus.NO_CONTENT)
  public void revokeAll(
      @AuthenticationPrincipal AuthenticatedUser principal, HttpServletRequest request) {
    // 세션마다 지우기 전에 종료 훅이 호출된다(SessionEndHook). 훅이 실패한 세션과 현재 기기는 남는다
    HttpSession current = request.getSession(false);
    userSessionService.revokeAll(principal.userId(), current == null ? null : current.getId());
    CurrentSessionEnder.end(request);
  }

  private static Optional<UUID> parse(String value) {
    try {
      return Optional.of(UUID.fromString(value));
    } catch (IllegalArgumentException e) {
      return Optional.empty();
    }
  }
}
