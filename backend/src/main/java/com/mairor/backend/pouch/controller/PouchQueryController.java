package com.mairor.backend.pouch.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.dto.PouchListQuery;
import com.mairor.backend.pouch.dto.PouchListResponse;
import com.mairor.backend.pouch.service.PouchQueryService;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 회원 개인 파우치 조회(API-POUCH-003·005). */
@Tag(name = "내 파우치", description = "회원 개인 파우치 항목의 목록·상세 조회.")
@RestController
@RequestMapping("/v1/users/me/pouch-items")
public class PouchQueryController {

  private final PouchQueryService queryService;

  public PouchQueryController(PouchQueryService queryService) {
    this.queryService = queryService;
  }

  @Operation(
      summary = "내 파우치 목록",
      description =
          "본인 파우치 항목을 카테고리·종류로 필터링해 페이지 단위로 조회한다. 전체 목록은 hasNext=false까지 조회한다."
              + " 응답의 pouchVersion이 페이지 사이 달라지면 누적 결과를 버리고 page=0부터 다시 조회한다.",
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "파우치 목록과 페이지 버전.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = PouchListResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description = "필터 코드 또는 page·size가 유효하지 않다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @AuthApiDocs.Unauthorized
  @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<PouchListResponse> list(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @Valid @ParameterObject @ModelAttribute PageQuery page,
      @ParameterObject @ModelAttribute PouchListQuery filters) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(queryService.list(principal.userId(), filters, page));
  }

  @Operation(
      summary = "내 파우치 항목 상세",
      description = "본인이 등록한 개인 파우치 복사본을 조회한다. 다른 회원의 항목과 존재하지 않는 항목은 모두 404다.",
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "개인 파우치 항목.",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = PouchItemResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description = "항목 ID가 UUID 형식이 아니다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "404",
      description = "항목이 없거나 본인 소유가 아니다. (NOT_FOUND)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @AuthApiDocs.Unauthorized
  @GetMapping(value = "/{pouchItemId}", produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<PouchItemResponse> get(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID pouchItemId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(queryService.get(principal.userId(), pouchItemId));
  }
}
