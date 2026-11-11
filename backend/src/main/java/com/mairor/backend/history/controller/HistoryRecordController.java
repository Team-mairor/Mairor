package com.mairor.backend.history.controller;

import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import com.mairor.backend.history.dto.ReportRecordSchema;
import com.mairor.backend.history.dto.ReportSummaryResponse;
import com.mairor.backend.history.service.HistoryRecordDeletionService;
import com.mairor.backend.history.service.HistoryRecordQueryService;
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
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.JsonNode;

/** 메이크업 리포트 목록 · 상세 · 삭제(API-REPORT-001~003, S15P31A306-404). 기록은 가이드 실행 완료(API-GUIDE-006)가 만든다. */
@Tag(name = "리포트", description = "가이드 실행을 마친 메이크업 리포트(완료 기록)의 목록 · 상세 · 삭제.")
@RestController
@RequestMapping("/v1/users/me/history-records")
public class HistoryRecordController {

  private final HistoryRecordQueryService queryService;
  private final HistoryRecordDeletionService deletionService;

  public HistoryRecordController(
      HistoryRecordQueryService queryService, HistoryRecordDeletionService deletionService) {
    this.queryService = queryService;
    this.deletionService = deletionService;
  }

  @Operation(
      summary = "내 리포트 목록",
      description =
          """
          실행을 마친 내 리포트를 완료 시각 최신순으로 준다.
          - 다른 기기에서 완료한 리포트도 같다.
          - 완성 사진이 없거나 지우는 중이면 completedPhoto 는 null 이다.
          - guideId 로 다시 따라 하기를 시작할 수 있다(새 실행 · 지금 파우치로 다시 매칭).
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(responseCode = "200", description = "리포트 한 페이지")
  @ApiResponse(responseCode = "400", description = "page · size 가 범위 밖이다. (VALIDATION_FAILED)")
  @AuthApiDocs.Unauthorized
  @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<PageResponse<ReportSummaryResponse>> list(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @Valid @ParameterObject @ModelAttribute PageQuery page) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(queryService.list(principal.userId(), page));
  }

  @Operation(
      summary = "리포트 상세",
      description =
          """
          완료할 때 고정한 단계 · 제품 · 색 · 사진 기록을 그대로 준다.
          - 이후 가이드 · 파우치가 바뀌어도 달라지지 않는다.
          - 사진은 url(사진 조회 API)로 받는다. 얼굴 등록 사진은 들어 있지 않다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "리포트 전체",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ReportRecordSchema.class)))
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.NotFound
  @GetMapping(path = "/{recordId}", produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<JsonNode> get(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID recordId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(queryService.get(principal.userId(), recordId));
  }

  @Operation(
      summary = "리포트 삭제",
      description =
          """
          리포트와 그 단계 사진 · 완성 사진 · 보관한 얼굴 등록 사진을 모두 지운다.
          - 사진 파일까지 다 지운 뒤에만 204 를 준다. 공용 가이드 · 파우치 · 다른 리포트는 지우지 않는다.
          - 일부를 못 지우면 503 이고 리포트는 남는다. 잠시 뒤 다시 요청하면 남은 것을 이어서 지운다.
          """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(responseCode = "204", description = "리포트와 사진을 모두 지웠다")
  @AuthApiDocs.Unauthorized
  @AuthApiDocs.CsrfRejected
  @AuthApiDocs.NotFound
  @ApiResponse(
      responseCode = "503",
      description = "사진 파일을 다 지우지 못했다. 잠시 뒤 다시 요청한다. (REPORT_DELETE_FAILED)")
  @DeleteMapping("/{recordId}")
  public ResponseEntity<Void> delete(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID recordId) {
    deletionService.delete(principal.userId(), recordId);
    return ResponseEntity.noContent().build();
  }
}
