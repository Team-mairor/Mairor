package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.request.RegisterAnalysisJobRequest;
import com.mairor.backend.analysis.dto.response.AnalysisJobReceiptResponse;
import com.mairor.backend.analysis.dto.response.InternalAnalysisJobResponse;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.common.web.OpenApiConfig;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 운영자용 분석 작업 등록·조회. 사용자 API(VIDEO-002·003)가 생기기 전 1차 MVP 에서 운영자가 저장소에 올린 영상으로 분석을 돌린다. 세션 대신 공유 토큰
 * 헤더({@code X-Internal-Token})로 지킨다.
 */
@Tag(
    name = "운영 · 분석 작업",
    description = "운영자가 저장소에 올린 영상으로 분석 작업을 넣고 상태를 본다. 공유 토큰 헤더(X-Internal-Token)가 필요하다.")
@RestController
@RequestMapping("/v1/internal/analysis-jobs")
public class InternalAnalysisJobController {

  private final AnalysisJobService analysisJobService;

  public InternalAnalysisJobController(AnalysisJobService analysisJobService) {
    this.analysisJobService = analysisJobService;
  }

  @Operation(
      summary = "분석 작업 등록",
      description =
          """
          저장소에 올린 영상 파일로 분석 작업을 넣는다. worker 가 차례로 집어 처리한다.

          - 같은 영상의 진행 중 작업이 있으면 새로 만들지 않고 그 작업을 돌려준다(JOINED_JOB).
          - 이미 있는 영상의 제목·채널·길이는 바꾸지 않는다.
          - 영상 파일이 없으면 접수는 되고, 작업이 SOURCE_NOT_FOUND 로 실패한다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(responseCode = "202", description = "접수(새 작업 또는 진행 중 작업에 합류)")
  @ApiResponse(responseCode = "400", description = "입력 형식 오류. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @PostMapping
  public ResponseEntity<AnalysisJobReceiptResponse> register(
      @Valid @RequestBody RegisterAnalysisJobRequest request) {
    return ResponseEntity.status(HttpStatus.ACCEPTED)
        .body(AnalysisJobReceiptResponse.from(analysisJobService.register(request.toCommand())));
  }

  @Operation(
      summary = "분석 작업 조회",
      description =
          """
          분석 작업의 상태·진행 단계·실패 원인과 영상 파일 원본 정보를 준다.

          - 실패해도 200 이며 failureCode·retryable 로 구분한다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.INTERNAL_TOKEN))
  @ApiResponse(responseCode = "200", description = "작업 상태")
  @ApiResponse(responseCode = "401", description = "공유 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 작업. (NOT_FOUND)")
  @GetMapping("/{jobId}")
  public InternalAnalysisJobResponse get(@PathVariable UUID jobId) {
    return InternalAnalysisJobResponse.from(analysisJobService.get(jobId));
  }
}
