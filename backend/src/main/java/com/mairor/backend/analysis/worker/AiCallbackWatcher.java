package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.log.AnalysisLogContext;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.external.ai.AiServerException;
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * AI 콜백이 늦은 작업을 확인한다(worker). AI 작업은 AI 서버 메모리에만 있어 AI 가 다시 시작되면 콜백 없이 사라진다({@code
 * docs/references/ai-api.md} "정할 것").
 *
 * <p>AI 에 맡긴 시각({@link AnalysisJob#aiTimeoutBaseline()}. 진행 숫자를 저장해도 바뀌지 않는다)에서 {@code
 * app.ai.callback-timeout}이 지난 작업마다 AI 에 상태를 묻는다: 끝났으면 콜백과 같이 반영하고(콜백을 놓친 경우), AI 에 작업이 없으면 {@code
 * ANALYSIS_TIMEOUT}, 아직 진행 중이면 두 배까지 기다린 뒤 {@code ANALYSIS_TIMEOUT}.
 */
@Component
@Profile("worker")
class AiCallbackWatcher {

  private static final Logger log = LoggerFactory.getLogger(AiCallbackWatcher.class);

  private final AnalysisJobRepository jobs;
  private final AiGuideJobClient client;
  private final AiResultService results;
  private final AiProperties properties;
  private final ObjectMapper objectMapper;
  private final Clock clock;

  AiCallbackWatcher(
      AnalysisJobRepository jobs,
      AiGuideJobClient client,
      AiResultService results,
      AiProperties properties,
      ObjectMapper objectMapper,
      Clock clock) {
    this.jobs = jobs;
    this.client = client;
    this.results = results;
    this.properties = properties;
    this.objectMapper = objectMapper;
    this.clock = clock;
  }

  @Scheduled(
      fixedDelayString = "${app.ai.watch-interval:60s}",
      initialDelayString = "${app.ai.watch-interval:60s}")
  void check() {
    Instant now = clock.instant();
    Instant late = now.minus(properties.callbackTimeout());
    Instant overdue = now.minus(properties.callbackTimeout().multipliedBy(2));
    for (AnalysisJob job : jobs.findAwaitingAiRequestedBefore(AnalysisStatus.RUNNING, late)) {
      // 영상은 지연 로딩이라 트랜잭션 밖에서는 읽지 않는다. 작업 칸 둘로 이어 본다
      try (var ignored = AnalysisLogContext.of(job.getId(), null, job.getAiJobId())) {
        checkOne(job.getAiJobId(), job.aiTimeoutBaseline().isBefore(overdue));
      } catch (RuntimeException e) {
        log.warn("AI 결과 확인 실패 jobId={} aiJobId={}", job.getId(), job.getAiJobId(), e);
      }
    }
  }

  void checkOne(String aiJobId, boolean overdue) {
    Optional<String> body;
    try {
      body = client.find(aiJobId);
    } catch (AiServerException e) {
      if (overdue) {
        results.timeout(aiJobId, "AI 서버에 닿지 못한 채 시간이 지났습니다: " + e.getMessage());
      } else {
        log.info("AI 결과 확인 보류 aiJobId={} {}", aiJobId, e.getMessage());
      }
      return;
    }
    if (body.isEmpty()) {
      results.timeout(aiJobId, "AI 서버에 작업이 없습니다(AI 재시작 또는 만료).");
      return;
    }
    JsonNode node = objectMapper.readTree(body.get());
    String status = node.path("status").asString("");
    if ("COMPLETED".equals(status) || "FAILED".equals(status)) {
      log.info("콜백 대신 상태 조회로 AI 결과 반영 aiJobId={} status={}", aiJobId, status);
      results.apply(
          new AiGuideJobCallbackRequest(
              node.path("jobId").asString(aiJobId),
              node.path("videoId").asString(null),
              status,
              node.get("guide"),
              node.get("area"),
              node.get("error")));
    } else if (overdue) {
      results.timeout(aiJobId, "AI 작업이 시간 안에 끝나지 않았습니다(AI 상태 " + status + ").");
    } else {
      log.info("AI 작업 진행 중이라 더 기다림 aiJobId={} status={}", aiJobId, status);
    }
  }
}
