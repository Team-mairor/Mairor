package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.request.RequestAnalysisJobRequest;
import com.mairor.backend.analysis.dto.response.AnalysisJobStatusResponse;
import com.mairor.backend.analysis.dto.response.AnalysisJobSummaryResponse;
import com.mairor.backend.analysis.dto.response.AnalysisRequestReceiptResponse;
import com.mairor.backend.analysis.service.AnalysisJobListService;
import com.mairor.backend.analysis.service.AnalysisJobStatusService;
import com.mairor.backend.analysis.service.AnalysisRequestReceipt;
import com.mairor.backend.analysis.service.AnalysisRequestService;
import com.mairor.backend.analysis.service.ReceiptType;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.ExampleObject;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회원의 분석 요청(API-VIDEO-002), 작업 상태(API-VIDEO-003), 내 분석 목록(API-VIDEO-007). 로그인이 필요하고 요청했거나 합류한 작업만
 * 본다({@code AnalysisJobAccess}). 진행 화면은 분석 상태 SSE 로 바뀔 때마다 받고, 상태 조회는 새로고침·홈 재확인과 SSE 를 못 쓸 때 쓴다.
 */
@Tag(name = "분석 작업", description = "영상 분석 요청과 내 분석 작업의 진행 상태.")
@RestController
@RequestMapping("/v1/users/me/analysis-jobs")
public class AnalysisJobController {

  private final AnalysisJobStatusService statusService;
  private final AnalysisRequestService requestService;
  private final AnalysisJobListService listService;

  public AnalysisJobController(
      AnalysisJobStatusService statusService,
      AnalysisRequestService requestService,
      AnalysisJobListService listService) {
    this.statusService = statusService;
    this.requestService = requestService;
    this.listService = listService;
  }

  @Operation(
      summary = "내 분석 목록",
      description =
          """
          내가 요청하거나 합류한 분석 작업 중 분석이 끝난 것을 요청 · 합류한 시각의 최신순으로 준다.
          - reviewStatus 로 가이드 검수 상태를 고른다(여러 값). 없으면 PENDING · APPROVED 이고, REJECTED 는 고를 때만 나온다.
          - guideId 는 검수 승인일 때만 있고, 그 값으로 바로 따라 하기를 시작한다.
          - 진행 중이거나 실패한 작업은 나오지 않는다(상태 조회 · 분석 상태 SSE 로 본다).
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "내 분석 목록 한 페이지",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              examples = @ExampleObject(name = "검수 중 · 승인", value = AnalysisApiDocs.LIST)))
  @ApiResponse(
      responseCode = "400",
      description =
          "reviewStatus 가 PENDING · APPROVED · REJECTED 가 아니거나 page · size 가 유효하지 않다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @AuthApiDocs.Unauthorized
  @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<PageResponse<AnalysisJobSummaryResponse>> list(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @Parameter(description = "고를 가이드 검수 상태. 없으면 PENDING · APPROVED", example = "PENDING")
          @RequestParam(name = "reviewStatus", required = false)
          List<ReviewStatus> reviewStatus,
      @Valid @ParameterObject @ModelAttribute PageQuery page) {
    return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(listService.list(principal.userId(), reviewStatus, page));
  }

  @Operation(
      summary = "분석 요청",
      description =
          """
          고른 영상(내부 videoId)의 분석을 요청한다. 재사용 → 합류 → 새 작업 순서로 가린다.
          - 승인 가이드가 있으면 200 REUSED_GUIDE(jobId=null), 진행 중 작업이 있으면 202 JOINED_JOB, 없으면 202 NEW_JOB. jobId 로 분석 상태 SSE 를 연다.
          - 요청할 때마다 YouTube 에서 공개 · CC BY 를 다시 확인한다(재사용 · 합류 포함).
          - 회원별 하루 새 작업 수에 한도가 있다(Asia/Seoul 0시 초기화). 재사용 · 합류는 세지 않는다.
          """,
      security = {
        @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE),
        @SecurityRequirement(name = OpenApiConfig.CSRF_TOKEN)
      })
  @ApiResponse(
      responseCode = "200",
      description = "승인 가이드 재사용(REUSED_GUIDE)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = AnalysisRequestReceiptResponse.class)))
  @ApiResponse(
      responseCode = "202",
      description = "새 작업(NEW_JOB) 또는 진행 중 작업에 합류(JOINED_JOB)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = AnalysisRequestReceiptResponse.class)))
  @ApiResponse(
      responseCode = "400",
      description = "videoId 가 UUID 가 아니다. (VALIDATION_FAILED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @AuthApiDocs.Unauthorized
  @ApiResponse(responseCode = "403", description = "X-CSRF-TOKEN 이 없거나 유효하지 않다. (CSRF_INVALID)")
  @ApiResponse(
      responseCode = "404",
      description = "없는 영상이다. (NOT_FOUND)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "409",
      description =
          "분석할 수 없는 영상이다(비공개 · 삭제 · 연령 제한 · 라이브 · CC BY 아님). (VIDEO_UNSUPPORTED_FOR_ANALYSIS)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "429",
      description =
          "오늘 새로 분석할 수 있는 횟수를 다 썼다. Retry-After(초) 헤더와 본문 resetAt(다음 초기화 시각)."
              + " (ANALYSIS_DAILY_LIMIT_EXCEEDED)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @ApiResponse(
      responseCode = "503",
      description = "YouTube 확인이 안 돼 지금은 요청할 수 없다. (VIDEO_ANALYSIS_UNAVAILABLE)",
      content =
          @Content(
              mediaType = MediaType.APPLICATION_JSON_VALUE,
              schema = @Schema(implementation = ErrorResponse.class)))
  @PostMapping(
      consumes = MediaType.APPLICATION_JSON_VALUE,
      produces = MediaType.APPLICATION_JSON_VALUE)
  public ResponseEntity<AnalysisRequestReceiptResponse> request(
      @AuthenticationPrincipal AuthenticatedUser principal,
      @RequestBody RequestAnalysisJobRequest request) {
    AnalysisRequestReceipt receipt =
        requestService.request(principal.userId(), request == null ? null : request.videoId());
    HttpStatus status =
        receipt.receiptType() == ReceiptType.REUSED_GUIDE ? HttpStatus.OK : HttpStatus.ACCEPTED;
    return ResponseEntity.status(status)
        .cacheControl(CacheControl.noStore())
        .body(AnalysisRequestReceiptResponse.from(receipt));
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
      description = "없는 작업이거나 내가 요청 · 합류한 작업이 아니다(구분하지 않는다). (NOT_FOUND)",
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
