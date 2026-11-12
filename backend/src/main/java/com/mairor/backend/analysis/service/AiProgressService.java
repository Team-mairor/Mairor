package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.log.AnalysisLogContext;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import java.util.List;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * AI 진행 알림({@code docs/references/ai-api.md} "진행 알림")의 숫자를 분석 작업에 저장한다.
 *
 * <p>AI 는 진행 알림을 다시 보내지 않고(재시도 없음) 다음 알림이나 최종 콜백이 숫자를 덮으므로, 받을 수 없는 알림은 저장하지 않고 버린다. 잘못된 알림 때문에 작업을
 * 실패시키지 않는다. 완료·실패는 최종 콜백({@link AiResultService})만 정한다.
 */
@Service
public class AiProgressService {

  /** 처리 결과. 저장한 경우 말고는 모두 버린 이유다. */
  public enum Outcome {
    SAVED,
    INVALID,
    UNKNOWN_JOB,
    NOT_AWAITING
  }

  /** 프레임을 보낸 작업에만 있는 칸. 셋 다 있거나 셋 다 {@code null}이다. */
  private static final List<String> AREA_COUNTS = List.of("frames", "landmarks", "area");

  private static final Logger log = LoggerFactory.getLogger(AiProgressService.class);

  private final AnalysisJobRepository jobs;
  private final AnalysisJobNotifier notifier;
  private final ObjectMapper objectMapper;

  AiProgressService(
      AnalysisJobRepository jobs, AnalysisJobNotifier notifier, ObjectMapper objectMapper) {
    this.jobs = jobs;
    this.notifier = notifier;
    this.objectMapper = objectMapper;
  }

  /**
   * @param body 진행 알림 본문 {@code {jobId, explanation, frames, landmarks, area}}
   */
  @Transactional
  public Outcome record(String body) {
    Optional<Progress> parsed = parse(body);
    if (parsed.isEmpty()) {
      return Outcome.INVALID;
    }
    Progress progress = parsed.get();
    Optional<AnalysisJob> found = jobs.lockByAiJobId(progress.aiJobId());
    if (found.isEmpty()) {
      try (var ignored = AnalysisLogContext.of(null, null, progress.aiJobId())) {
        log.info("모르는 AI 작업의 진행 알림이라 버림 aiJobId={}", progress.aiJobId());
      }
      return Outcome.UNKNOWN_JOB;
    }
    AnalysisJob job = found.get();
    try (var ignored = AnalysisLogContext.of(job)) {
      return recordFor(job, progress);
    }
  }

  private Outcome recordFor(AnalysisJob job, Progress progress) {
    if (!job.recordAiProgress(progress.json())) {
      log.info(
          "AI 결과를 기다리는 작업이 아니라 진행 알림을 버림 jobId={} aiJobId={} status={}",
          job.getId(),
          progress.aiJobId(),
          job.getStatus());
      return Outcome.NOT_AWAITING;
    }
    notifier.changed(job.getId());
    log.debug("AI 진행 숫자 저장 jobId={} progress={}", job.getId(), progress.json());
    return Outcome.SAVED;
  }

  /**
   * 본문을 읽고 숫자를 검사한다. 저장할 JSON 은 검사를 통과한 네 칸만 다시 만든다(모르는 칸은 버린다).
   *
   * @return 받을 수 없는 본문이면 빈 값(이유는 로그)
   */
  private Optional<Progress> parse(String body) {
    JsonNode root;
    try {
      root = body == null || body.isBlank() ? null : objectMapper.readTree(body);
    } catch (JacksonException e) {
      return invalid("JSON 이 아님", body);
    }
    if (root == null || !root.isObject()) {
      return invalid("본문이 객체가 아님", body);
    }
    String aiJobId = root.path("jobId").asString("");
    if (aiJobId.isBlank()) {
      return invalid("jobId 없음", body);
    }

    ObjectNode json = objectMapper.createObjectNode();
    Optional<ObjectNode> explanation = count(root.get("explanation"));
    if (explanation.isEmpty()) {
      return invalid("explanation 이 {done, total} 이 아님", body);
    }
    json.set("explanation", explanation.get());

    long present = AREA_COUNTS.stream().filter(name -> isPresent(root.get(name))).count();
    if (present != 0 && present != AREA_COUNTS.size()) {
      return invalid("frames·landmarks·area 는 셋 다 있거나 셋 다 null 이어야 함", body);
    }
    for (String name : AREA_COUNTS) {
      if (present == 0) {
        json.putNull(name);
        continue;
      }
      Optional<ObjectNode> value = count(root.get(name));
      if (value.isEmpty()) {
        return invalid(name + " 이 {done, total} 이 아님", body);
      }
      json.set(name, value.get());
    }
    return Optional.of(new Progress(aiJobId, objectMapper.writeValueAsString(json)));
  }

  /** {@code {done, total}}: 둘 다 정수이고 {@code 0 <= done <= total}. */
  private Optional<ObjectNode> count(JsonNode node) {
    if (node == null || !node.isObject()) {
      return Optional.empty();
    }
    JsonNode done = node.get("done");
    JsonNode total = node.get("total");
    if (!isWholeNumber(done) || !isWholeNumber(total)) {
      return Optional.empty();
    }
    long doneValue = done.longValue();
    long totalValue = total.longValue();
    if (doneValue < 0 || doneValue > totalValue) {
      return Optional.empty();
    }
    ObjectNode count = objectMapper.createObjectNode();
    count.put("done", doneValue);
    count.put("total", totalValue);
    return Optional.of(count);
  }

  private static boolean isWholeNumber(JsonNode node) {
    return node != null && node.isIntegralNumber() && node.canConvertToLong();
  }

  private static boolean isPresent(JsonNode node) {
    return node != null && !node.isNull();
  }

  private static Optional<Progress> invalid(String reason, String body) {
    String brief = body == null ? "" : body.replaceAll("\\s+", " ").trim();
    log.warn(
        "받을 수 없는 AI 진행 알림이라 버림 reason={} body={}",
        reason,
        brief.length() > 300 ? brief.substring(0, 300) + "…" : brief);
    return Optional.empty();
  }

  private record Progress(String aiJobId, String json) {}
}
