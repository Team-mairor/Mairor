package com.mairor.backend.pouch.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.pouch.dto.PouchUpdateRequest;
import com.mairor.backend.pouch.dto.PouchUpdateResponse;
import com.mairor.backend.pouch.service.PouchUpdateService;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 내 파우치 항목 수정(API-POUCH-006). */
@Tag(name = "내 파우치", description = "회원 개인 파우치 항목 수정.")
@RestController
@RequestMapping("/v1/users/me/pouch-items")
public class PouchUpdateController {

  private final PouchUpdateService updateService;

  public PouchUpdateController(PouchUpdateService updateService) {
    this.updateService = updateService;
  }

  @Operation(
      summary = "파우치 항목 수정",
      description = "요청에 포함된 필드만 수정한다. CATALOG 직접 입력은 개인 항목을 MANUAL로 전환하며 공용 카탈로그는 변경하지 않는다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "200",
      description = "수정된 개인 파우치 항목과 pouchVersion.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = PouchUpdateResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description = "요청 필드 또는 최종 제품·호수 상태가 유효하지 않다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "404",
      description = "항목이 없거나 현재 회원 소유가 아니다.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "409",
      description = "같은 정규화 제품이 이미 등록됐다. (POUCH_DUPLICATE)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(responseCode = "403", description = "X-CSRF-TOKEN 이 없거나 유효하지 않다. (CSRF_INVALID)")
  @AuthApiDocs.Unauthorized
  @PatchMapping(
      value = "/{pouchItemId}",
      consumes = MediaType.APPLICATION_JSON_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  public PouchUpdateResponse update(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @PathVariable UUID pouchItemId,
      @RequestBody PouchUpdateRequest request) {
    return updateService.update(principal.userId(), pouchItemId, request);
  }
}
