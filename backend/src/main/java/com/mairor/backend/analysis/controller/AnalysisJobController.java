package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.response.AnalysisJobStatusResponse;
import com.mairor.backend.analysis.service.AnalysisJobStatusService;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회원의 분석 작업 상태(API-VIDEO-003). 로그인이 필요하고 본인이 요청한 작업만 본다({@code AnalysisJobAccess}). 진행 화면은 분석 상태
 * SSE 로 바뀔 때마다 받고, 이 조회는 새로고침·홈 재확인과 SSE 를 못 쓸 때 쓴다.
 */
@Tag(name = "분석 작업", description = "내 영상 분석 작업의 진행 상태.")
@RestController
@RequestMapping("/v1/users/me/analysis-jobs")
public class AnalysisJobController {

  private final AnalysisJobStatusService statusService;

  public AnalysisJobController(AnalysisJobStatusService statusService) {
    this.statusService = statusService;
  }

  @Operation(
      summary = "분석 작업 상태",
      description =
          """
          분석 작업의 진행 단계·단계 안 숫자·검수 상태·실패 원인을 한 번 준다.

          - 실패해도 200 이며 failureCode·retryable 로 구분한다.
          - stageProgress 는 지금 단계 안의 숫자이고 전체 %가 아니다. 완료 여부는 status 로만 본다.
          - foundProducts 는 제품 인식이 연결되기 전까지 빈 목록이다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "작업 상태",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = AnalysisJobStatusResponse.class),
              examples = @ExampleObject(name = "가이드 생성 중", value = AnalysisApiDocs.STATUS_RUNNING)))
  @ApiResponse(
      responseCode = "404",
      description = "없는 작업이거나 내가 요청한 작업이 아니다(구분하지 않는다). (NOT_FOUND)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @AuthApiDocs.Unauthorized
  @GetMapping("/{jobId}")
  public ResponseEntity<AnalysisJobStatusResponse> get(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID jobId) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(AnalysisJobStatusResponse.from(statusService.get(principal.userId(), jobId)));
  }
}
