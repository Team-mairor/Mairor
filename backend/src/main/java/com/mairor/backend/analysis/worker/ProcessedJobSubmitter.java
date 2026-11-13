package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.log.AnalysisLogContext;
import com.mairor.backend.analysis.service.AiFrameDelivery;
import com.mairor.backend.analysis.service.ProcessorJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore.ProcessedJob;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.external.ai.AiServerException;
import com.mairor.backend.common.storage.ObjectNotFoundException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import com.mairor.backend.common.storage.StorageProperties;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 노트북이 끝낸 작업을 AI 에 맡긴다(worker, S15P31A306-358). 저장소의 요청 JSON 을 읽어 검사하고({@link ProcessorRequest}),
 * 가이드 입력을 가이드 행에 남긴 뒤 {@code callbackUrl} · {@code progressUrl} · 프레임 주소를 바꿔 AI 에 보낸다. 그 뒤(AI 콜백 →
 * 검수)는 BE 단계 추출 흐름과 같다({@link BuildGuideStep}).
 *
 * <p>연결 모드를 꺼도 이미 노트북이 끝낸 작업은 AI 에 맡긴다(새 완료 알림은 생기지 않는다). 연결 모드에서는 노트북을 너무 오래 기다린 작업도 여기서
 * 끝낸다({@link ProcessorJobService#expireWaiting()}은 연결 모드가 아니면 아무것도 하지 않는다).
 */
@Component
@Profile("worker")
public class ProcessedJobSubmitter {

  private static final Logger log = LoggerFactory.getLogger(ProcessedJobSubmitter.class);

  /** 노트북 응답 없음 경고를 다시 남기는 간격. Grafana 규칙은 15분 창에서 세어 경고 사이에 알림이 풀리지 않는다. */
  static final Duration STALL_WARN_REPEAT = Duration.ofMinutes(10);

  private final AnalysisJobStore store;
  private final ProcessorJobService processorJobs;
  private final ObjectStorage storage;
  private final StorageProperties storageProperties;
  private final AiGuideJobClient client;
  private final AiProperties ai;
  private final WorkerProperties worker;
  private final ObjectMapper objectMapper;
  private final AiFrameDelivery frameDelivery;
  // 스케줄 스레드 하나에서만 바뀐다
  private Instant lastStallWarning;

  public ProcessedJobSubmitter(
      AnalysisJobStore store,
      ProcessorJobService processorJobs,
      ObjectStorage storage,
      StorageProperties storageProperties,
      AiGuideJobClient client,
      AiProperties ai,
      WorkerProperties worker,
      ObjectMapper objectMapper,
      AiFrameDelivery frameDelivery) {
    this.store = store;
    this.processorJobs = processorJobs;
    this.storage = storage;
    this.storageProperties = storageProperties;
    this.client = client;
    this.ai = ai;
    this.worker = worker;
    this.objectMapper = objectMapper;
    this.frameDelivery = frameDelivery;
  }

  @Scheduled(fixedDelayString = "${app.analysis.processor.submit-interval:5s}")
  void poll() {
    // 스위치를 꺼도 이미 노트북이 끝낸 작업은 AI 에 맡긴다(꺼진 동안 멈추지 않게). 기다림 시간 초과는 연결 모드에서만 본다
    try {
      int expired = processorJobs.expireWaiting();
      if (expired > 0) {
        log.warn("노트북을 기다리다 끝낸 작업 {}개", expired);
      }
      processorJobs.stalled().ifPresent(this::warnStalled);
      while (submitNext()) {
        // 밀린 작업을 이어서 맡긴다
      }
    } catch (RuntimeException e) {
      log.error("노트북 결과를 AI 에 맡기지 못했습니다. 다음 주기에 다시 시도합니다.", e);
    }
  }

  /**
   * 노트북 응답 없음 경고. Grafana 알림이 이 줄을 세므로(S15P31A306-406) 같은 상태가 이어지면 {@link #STALL_WARN_REPEAT}에 한 번만
   * 남긴다.
   */
  void warnStalled(ProcessorJobService.Stall stall) {
    if (lastStallWarning != null
        && Duration.between(lastStallWarning, stall.checkedAt()).compareTo(STALL_WARN_REPEAT) < 0) {
      return;
    }
    lastStallWarning = stall.checkedAt();
    log.atWarn()
        .setMessage("노트북이 작업을 가져가지 않음 waiting={} oldestWaitMs={}")
        .addArgument(stall.waiting())
        .addArgument(stall.oldestWait().toMillis())
        .addKeyValue("waiting", stall.waiting())
        .addKeyValue("oldest_wait_ms", stall.oldestWait().toMillis())
        .log();
  }

  /**
   * 노트북이 끝낸 작업 하나를 AI 에 맡긴다.
   *
   * @return 처리한 작업이 있었으면 true(실패로 끝냈어도)
   */
  public boolean submitNext() {
    Optional<ProcessedJob> next = store.nextProcessed();
    if (next.isEmpty()) {
      return false;
    }
    ProcessedJob job = next.get();
    try (var ignored = AnalysisLogContext.of(job.jobId(), job.youtubeVideoId(), null)) {
      submitOrFail(job);
    }
    return true;
  }

  private void submitOrFail(ProcessedJob job) {
    try {
      submit(job);
    } catch (AnalysisStepException e) {
      log.warn(
          "노트북 결과로 AI 요청 실패 jobId={} code={} message={}",
          job.jobId(),
          e.code(),
          e.getMessage(),
          e.getCause());
      store.fail(job.jobId(), e.code(), e.getMessage());
    } catch (RuntimeException e) {
      log.error("노트북 결과 처리 중 예기치 않은 오류 jobId={}", job.jobId(), e);
      store.fail(job.jobId(), AnalysisFailureCode.INTERNAL_ERROR, null);
    }
  }

  private void submit(ProcessedJob job) {
    String json = read(job);
    ProcessorRequest request =
        ProcessorRequest.parse(
            objectMapper, json, job.youtubeVideoId(), storageProperties.s3().bucket());
    store.saveGuideInput(job.jobId(), request.guideInputJson());
    // 로컬 저장소처럼 AI 가 받을 수 없는 주소만 주면 프레임을 빼고 맡긴다(BuildGuideStep 과 같은 판단)
    boolean sendFrames = frameDelivery.enabled() && !request.frames().isEmpty();
    if (sendFrames) {
      // AI 결과 검사(-363)가 "프레임을 보낸 작업이면 영역이 있어야 한다"를 이 칸으로 본다. 보내지 않으면 남기지 않는다
      store.recordFramesManifest(job.jobId(), job.requestKey());
    }
    String callbackUrl = ai.callbackBaseUrl() + BuildGuideStep.CALLBACK_PATH;
    String progressUrl = ai.callbackBaseUrl() + BuildGuideStep.PROGRESS_PATH;
    String body;
    try {
      body =
          sendFrames
              ? request.aiRequest(
                  callbackUrl,
                  progressUrl,
                  key -> storage.presignGet(key, ai.frameUrlTtl()).toString())
              : request.aiRequestWithoutFrames(callbackUrl, progressUrl);
    } catch (StorageException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "프레임 주소를 만들지 못했습니다: " + e.getMessage(), e);
    }
    String aiJobId;
    try {
      aiJobId = client.submit(body);
    } catch (AiServerException e) {
      throw new AnalysisStepException(BuildGuideStep.failureCode(e), e.getMessage(), e);
    }
    store.awaitAi(job.jobId(), aiJobId);
    int frames = sendFrames ? request.frames().size() : 0;
    // 이 줄부터 AI 작업 ID 를 붙여 AI 로그와 이어 본다
    try (var ignored = AnalysisLogContext.of(null, null, aiJobId)) {
      log.atInfo()
          .setMessage("노트북 결과로 AI 가이드 생성 요청 jobId={} aiJobId={} steps={} frames={} requestBytes={}")
          .addArgument(job.jobId())
          .addArgument(aiJobId)
          .addArgument(request.stepCount())
          .addArgument(frames)
          .addArgument(body.length())
          .addKeyValue("steps", request.stepCount())
          .addKeyValue("frames", frames)
          .addKeyValue("request_bytes", body.length())
          .log();
    }
  }

  private String read(ProcessedJob job) {
    Path dir = worker.workDir().resolve(job.jobId().toString());
    Path file = dir.resolve("guide_job_request.json");
    try {
      Files.createDirectories(dir);
      storage.download(job.requestKey(), file);
      return Files.readString(file, StandardCharsets.UTF_8);
    } catch (ObjectNotFoundException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.PROCESSOR_OUTPUT_INVALID,
          "요청 JSON 이 저장소에 없습니다: " + job.requestKey(),
          e);
    } catch (StorageException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "요청 JSON 을 받지 못했습니다: " + e.getMessage(), e);
    } catch (IOException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.INTERNAL_ERROR, "요청 JSON 을 읽지 못했습니다: " + e.getMessage(), e);
    } finally {
      try {
        Files.deleteIfExists(file);
        Files.deleteIfExists(dir);
      } catch (IOException e) {
        log.warn("작업 폴더를 지우지 못했습니다: {}", dir);
      }
    }
  }
}
