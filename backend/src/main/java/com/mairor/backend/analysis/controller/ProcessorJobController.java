package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.request.ProcessorCompleteRequest;
import com.mairor.backend.analysis.dto.request.ProcessorFailRequest;
import com.mairor.backend.analysis.dto.request.ProcessorProgressRequest;
import com.mairor.backend.analysis.dto.response.ProcessorClaimResponse;
import com.mairor.backend.analysis.service.ProcessorJobService;
import com.mairor.backend.common.web.OpenApiConfig;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 영상 전처리 노트북 API(S15P31A306-357). 노트북이 작업을 가져가 영상 받기 · 단계 추출 · 프레임 · AI 요청 JSON 을 만들고 결과를 알린다. 세션
 * 대신 노트북 토큰 헤더({@code X-Processor-Token})로 지킨다. 계약은 {@code docs/references/processor-api.md}.
 */
@Tag(
    name = "노트북 · 분석 작업",
    description = "영상 전처리 노트북이 분석 작업을 가져가고 결과를 알린다. X-Processor-Token 이 필요하다.")
@RestController
@RequestMapping("/v1/internal/processor/jobs")
public class ProcessorJobController {

  private final ProcessorJobService service;

  public ProcessorJobController(ProcessorJobService service) {
    this.service = service;
  }

  @Operation(
      summary = "작업 가져가기",
      description =
          """
          가장 오래 기다린 분석 작업 하나에 임대를 걸어 내준다.
          - 임대 안에 완료 · 실패 · 진행 알림이 없으면 다시 내주고, 정해진 횟수를 넘기면 그 작업은 재시도 가능 실패로 끝난다.
          - 연결 모드가 꺼져 있으면 늘 204 다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.PROCESSOR_TOKEN))
  @ApiResponse(responseCode = "200", description = "내준 작업")
  @ApiResponse(responseCode = "204", description = "할 일이 없다")
  @ApiResponse(responseCode = "401", description = "노트북 토큰이 없거나 다름. (UNAUTHORIZED)")
  @PostMapping("/claim")
  public ResponseEntity<ProcessorClaimResponse> claim() {
    return service
        .claim()
        .map(claim -> ResponseEntity.ok(ProcessorClaimResponse.from(claim)))
        .orElseGet(() -> ResponseEntity.noContent().build());
  }

  @Operation(
      summary = "작업 완료 알림",
      description =
          """
          올린 AI 요청 JSON 의 저장소 키를 알린다. 이후 BE worker 가 그 JSON 으로 AI 에 가이드 생성을 맡긴다(S15P31A306-358).
          - 같은 키로 다시 알리면 아무것도 바꾸지 않고 202 다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.PROCESSOR_TOKEN))
  @ApiResponse(responseCode = "202", description = "받음")
  @ApiResponse(responseCode = "400", description = "키가 이 작업 경로 밖이거나 저장소에 없음. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "노트북 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 작업. (NOT_FOUND)")
  @ApiResponse(
      responseCode = "409",
      description = "노트북이 처리 중인 작업이 아니거나 다른 키로 이미 끝남. (PROCESSOR_JOB_CONFLICT)")
  @PostMapping("/{jobId}/complete")
  public ResponseEntity<Void> complete(
      @PathVariable UUID jobId, @RequestBody ProcessorCompleteRequest request) {
    service.complete(jobId, request == null ? null : request.guideJobRequestKey());
    return ResponseEntity.accepted().build();
  }

  @Operation(
      summary = "작업 실패 알림",
      description =
          """
          처리하지 못한 이유를 알린다. 작업은 실패로 끝나고 재시도 여부는 실패 코드로 정한다.
          - 이미 실패로 끝난 작업이면 아무것도 바꾸지 않고 204 다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.PROCESSOR_TOKEN))
  @ApiResponse(responseCode = "204", description = "받음")
  @ApiResponse(responseCode = "400", description = "실패 코드가 없음. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "노트북 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 작업. (NOT_FOUND)")
  @ApiResponse(responseCode = "409", description = "노트북이 처리 중인 작업이 아님. (PROCESSOR_JOB_CONFLICT)")
  @PostMapping("/{jobId}/fail")
  public ResponseEntity<Void> fail(
      @PathVariable UUID jobId, @RequestBody ProcessorFailRequest request) {
    service.fail(
        jobId,
        request == null ? null : request.code(),
        request == null ? null : request.retryable(),
        request == null ? null : request.message());
    return ResponseEntity.noContent().build();
  }

  @Operation(
      summary = "작업 진행 알림",
      description =
          """
          지금 단계를 알린다. 앱 로딩 화면(분석 상태 SSE)에 보이고 임대가 늘어난다.
          - 단계는 앞으로만 움직인다(늦게 온 알림이 되돌리지 않는다).
          """,
      security = @SecurityRequirement(name = OpenApiConfig.PROCESSOR_TOKEN))
  @ApiResponse(responseCode = "204", description = "받음")
  @ApiResponse(responseCode = "400", description = "노트북 단계가 아님. (VALIDATION_FAILED)")
  @ApiResponse(responseCode = "401", description = "노트북 토큰이 없거나 다름. (UNAUTHORIZED)")
  @ApiResponse(responseCode = "404", description = "없는 작업. (NOT_FOUND)")
  @ApiResponse(responseCode = "409", description = "노트북이 처리 중인 작업이 아님. (PROCESSOR_JOB_CONFLICT)")
  @PostMapping("/{jobId}/progress")
  public ResponseEntity<Void> progress(
      @PathVariable UUID jobId, @RequestBody ProcessorProgressRequest request) {
    service.progress(
        jobId,
        request == null ? null : request.stage(),
        request == null ? null : request.percent());
    return ResponseEntity.noContent().build();
  }
}
