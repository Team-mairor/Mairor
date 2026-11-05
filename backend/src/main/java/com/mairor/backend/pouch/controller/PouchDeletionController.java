package com.mairor.backend.pouch.controller;

import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.pouch.service.PouchDeletionService;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 내 파우치 항목 삭제(API-POUCH-007). */
@Tag(name = "내 파우치", description = "회원 개인 파우치 항목 삭제.")
@RestController
@RequestMapping("/v1/users/me/pouch-items")
public class PouchDeletionController {

  private final PouchDeletionService deletionService;

  public PouchDeletionController(PouchDeletionService deletionService) {
    this.deletionService = deletionService;
  }

  @Operation(
      summary = "파우치 항목 삭제",
      description = "본인 파우치 항목을 삭제한다. 이미 시작한 실행·완료 리포트와 공용 카탈로그는 변경하지 않는다.",
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "204", description = "삭제 완료. 응답 본문 없음.")
  @ApiResponse(
      responseCode = "400",
      description = "항목 ID가 UUID 형식이 아니다.",
      content =
          @Content(
              mediaType = "application/json",
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "404",
      description = "항목이 없거나 현재 회원 소유가 아니다.",
      content =
          @Content(
              mediaType = "application/json",
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(responseCode = "403", description = "X-CSRF-TOKEN 이 없거나 유효하지 않다. (CSRF_INVALID)")
  @AuthApiDocs.Unauthorized
  @DeleteMapping("/{pouchItemId}")
  public ResponseEntity<Void> delete(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID pouchItemId) {
    deletionService.delete(principal.userId(), pouchItemId);
    return ResponseEntity.noContent().build();
  }
}
