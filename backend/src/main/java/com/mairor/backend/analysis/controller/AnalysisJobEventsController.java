package com.mairor.backend.analysis.controller;

import com.mairor.backend.analysis.dto.response.AnalysisJobStatusResponse;
import com.mairor.backend.analysis.service.AnalysisJobAccess;
import com.mairor.backend.analysis.sse.SseHub;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.web.OpenApiConfig;
import com.mairor.backend.users.controller.AuthApiDocs;
import com.mairor.backend.users.support.AuthenticatedUser;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.UUID;
import org.springframework.context.annotation.Profile;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 회원의 분석 상태 SSE(ADR-012). 연결을 열어 두면 상태가 바뀔 때마다 {@code status} 이벤트로 {@code AnalysisJobStatus} 전체를
 * 보낸다. api 프로세스에서만 뜬다(worker 의 변경은 DB 변경 알림으로 api 에 온다).
 */
@Tag(name = "분석 작업", description = "내 영상 분석 작업의 진행 상태.")
@RestController
@RequestMapping("/v1/users/me/analysis-jobs")
@Profile("!worker")
public class AnalysisJobEventsController {

  /** nginx 가 SSE 응답을 모아 두지 않고 바로 넘기게 한다. */
  static final String NO_BUFFERING = "X-Accel-Buffering";

  private final AnalysisJobAccess access;
  private final SseHub hub;

  public AnalysisJobEventsController(AnalysisJobAccess access, SseHub hub) {
    this.access = access;
    this.hub = hub;
  }

  @Operation(
      summary = "분석 상태 실시간",
      description =
          """
          연결을 열어 두면 분석 작업 상태가 바뀔 때마다 status 이벤트로 상태 전체를 보낸다(text/event-stream).

          - 연결하면 지금 상태를 먼저 보낸다. 실패·검수 승인·반려를 보낸 뒤 서버가 닫는다.
          - 검수 대기(COMPLETED · reviewStatus PENDING)에서는 열려 있으므로 화면을 떠날 때 FE 가 닫는다.
          - 끊기면 EventSource 가 다시 붙고 지금 상태를 다시 받는다. 쓸 수 없으면 상태 조회를 폴링한다.
          """,
      security = @SecurityRequirement(name = OpenApiConfig.SESSION_COOKIE))
  @ApiResponse(
      responseCode = "200",
      description = "status 이벤트 흐름. 이벤트마다 data 는 분석 작업 상태 JSON 이다.",
      content =
          @Content(
              mediaType = MediaType.TEXT_EVENT_STREAM_VALUE,
              schema = @Schema(implementation = AnalysisJobStatusResponse.class)))
  @ApiResponse(
      responseCode = "404",
      description =
          "없는 작업이거나 내가 요청·합류한 작업이 아니다(구분하지 않는다). EventSource 가 JSON 을 받지 않아 본문은 없다. (NOT_FOUND)")
  @AuthApiDocs.Unauthorized
  @GetMapping("/{jobId}/events")
  public ResponseEntity<SseEmitter> events(
      @AuthenticationPrincipal AuthenticatedUser principal, @PathVariable UUID jobId) {
    try {
      access.load(principal.userId(), jobId);
    } catch (BusinessException e) {
      // EventSource 는 text/event-stream 만 받겠다고 보내서 JSON 오류 본문을 쓸 수 없다(쓰려 하면 500). 본문 없이 상태만 준다
      return ResponseEntity.status(e.status()).build();
    }
    return ResponseEntity.ok()
        .header(NO_BUFFERING, "no")
        .cacheControl(CacheControl.noStore())
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(hub.subscribe(principal.userId(), jobId));
  }
}
