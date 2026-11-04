package com.mairor.backend.pouch.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.pouch.dto.PouchRegistrationRequest;
import com.mairor.backend.pouch.dto.PouchRegistrationResponse;
import com.mairor.backend.pouch.service.PouchRegistrationService;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** 내 파우치 항목 등록(API-POUCH-004). */
@Tag(name = "내 파우치", description = "회원 개인 파우치 항목 등록.")
@RestController
@RequestMapping("/v1/users/me/pouch-items")
public class PouchRegistrationController {

  private final PouchRegistrationService registration;

  public PouchRegistrationController(PouchRegistrationService registration) {
    this.registration = registration;
  }

  @Operation(
      summary = "파우치 항목 등록",
      description =
          "CATALOG 항목은 기존 카탈로그에서 검증한 값을 개인 항목에 복사하고, MANUAL 항목은 개인 파우치에만 저장한다."
              + " 공용 카탈로그 데이터를 생성·수정하거나 수집하지 않는다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "201",
      description = "개인 파우치 항목과 갱신된 pouchVersion.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = PouchRegistrationResponse.class)))
  @ApiResponse(responseCode = "400", description = "입력 형식 또는 제품·호수 조합이 잘못됐다.")
  @ApiResponse(responseCode = "409", description = "같은 정규화 제품이 이미 등록됐다. (POUCH_DUPLICATE)")
  @ApiResponse(responseCode = "403", description = "X-CSRF-TOKEN 이 없거나 유효하지 않다. (CSRF_INVALID)")
  @AuthApiDocs.Unauthorized
  @PostMapping(
      consumes = MediaType.APPLICATION_JSON_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  @ResponseStatus(HttpStatus.CREATED)
  public PouchRegistrationResponse register(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @RequestBody PouchRegistrationRequest request) {
    UUID userId = principal.userId();
    return registration.register(userId, request);
  }
}
