package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.service.AiResultService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * AI 서버가 부르는 콜백({@code docs/references/ai-api.md}). AI 는 인증 헤더를 붙이지 못해 공유 토큰을 요구하지 않는다. 대신 nginx 가
 * {@code /api/v1/internal/ai/}를 바깥에서 막고, AI 는 {@code core} 네트워크로 {@code api:8080}에 바로 붙는다.
 */
@Tag(name = "내부 · AI 콜백", description = "AI 서버가 가이드 생성 결과를 보낸다. 바깥(nginx)에서는 막혀 있고 내부망에서만 부른다.")
@RestController
@RequestMapping("/v1/internal/ai/guide-jobs")
public class AiCallbackController {

  private final AiResultService aiResultService;

  public AiCallbackController(AiResultService aiResultService) {
    this.aiResultService = aiResultService;
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
  @ApiResponse(responseCode = "404", description = "모르는 AI 작업. (NOT_FOUND)")
  @PostMapping("/callback")
  public ResponseEntity<Void> callback(@RequestBody AiGuideJobCallbackRequest request) {
    aiResultService.apply(request);
    return ResponseEntity.noContent().build();
  }
}
