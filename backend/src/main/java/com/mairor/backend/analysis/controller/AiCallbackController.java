package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.dto.request.AiGuideJobProgressRequest;
import com.mairor.backend.analysis.service.AiProgressService;
import com.mairor.backend.analysis.service.AiResultService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * AI 서버가 부르는 콜백·진행 알림({@code docs/references/ai-api.md}). AI 는 인증 헤더를 붙이지 못해 공유 토큰을 요구하지 않는다. 대신
 * nginx 가 {@code /api/v1/internal/ai/}를 바깥에서 막고, AI 는 {@code core} 네트워크로 {@code api:8080}에 바로 붙는다.
 */
@Tag(
    name = "내부 · AI 콜백",
    description = "AI 서버가 가이드 생성 결과와 진행 숫자를 보낸다. 바깥(nginx)에서는 막혀 있고 내부망에서만 부른다.")
@RestController
@RequestMapping(AiCallbackController.BASE_PATH)
public class AiCallbackController {

  /** AI 가 부르는 주소의 앞부분. nginx 가 {@code /api} + 이 경로를 바깥에서 막는다. */
  public static final String BASE_PATH = "/v1/internal/ai/guide-jobs";

  /** 진행 알림 주소. 가이드 생성 요청의 {@code progressUrl}로 AI 에 넘긴다. */
  public static final String PROGRESS_PATH = BASE_PATH + "/progress";

  private final AiResultService aiResultService;
  private final AiProgressService aiProgressService;

  public AiCallbackController(
      AiResultService aiResultService, AiProgressService aiProgressService) {
    this.aiResultService = aiResultService;
    this.aiProgressService = aiProgressService;
  }

  @Operation(
      summary = "가이드 생성 결과",
      description =
          """
          AI 가이드 생성 작업의 결과를 받아 가이드에 쉬운 설명·영역을 저장한다.

          - COMPLETED 면 검수 대기(PENDING)가 되고, FAILED 면 분석 작업이 실패로 끝난다.
          - 이미 끝난 작업의 콜백(재전송)은 바꾸지 않고 204 로 답한다.
          - 공유 토큰을 쓰지 않고 내부망에서만 닿는다.
          """)
  @ApiResponse(responseCode = "204", description = "반영(또는 이미 반영됨)")
  @ApiResponse(responseCode = "400", description = "필수 칸이 없음. (VALIDATION_FAILED)")
  @ApiResponse(
      responseCode = "503",
      description =
          "아직 모르는 AI 작업. AI 접수 직후라 작업 ID 를 저장하기 전일 수 있어 AI 가 다시 보낸다. (SERVICE_UNAVAILABLE)")
  @PostMapping("/callback")
  public ResponseEntity<Void> callback(@RequestBody AiGuideJobCallbackRequest request) {
    aiResultService.apply(request);
    return ResponseEntity.noContent().build();
  }

  @Operation(
      summary = "가이드 생성 진행",
      description =
          """
          AI 가이드 생성 작업의 진행 숫자(설명·사진·얼굴 점·영역)를 받아 분석 작업에 저장한다.

          - 받을 수 없는 알림(모르는 작업, 이미 끝난 작업, 형식·숫자 오류)도 저장하지 않고 204 로 답한다. AI 는 진행 알림을 다시 보내지 않는다.
          - 완료·실패는 이 알림이 아니라 결과 콜백으로만 정해진다.
          - 공유 토큰을 쓰지 않고 내부망에서만 닿는다.
          """,
      requestBody =
          @io.swagger.v3.oas.annotations.parameters.RequestBody(
              content =
                  @Content(schema = @Schema(implementation = AiGuideJobProgressRequest.class))))
  @ApiResponse(responseCode = "204", description = "받음(저장했거나 버림)")
  @PostMapping("/progress")
  public ResponseEntity<Void> progress(@RequestBody(required = false) String body) {
    aiProgressService.record(body);
    return ResponseEntity.noContent().build();
  }
}
