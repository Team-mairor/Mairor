package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import tools.jackson.databind.json.JsonMapper;

/**
 * 영상 전처리 노트북 API(S15P31A306-357): 임대 · 다시 내주기 · 반복 만료 실패, 완료 · 실패 · 진행 알림, 노트북 토큰, 연결 모드에서 worker 가
 * 대기 작업을 집지 않는 것을 PostgreSQL 로 확인한다. 임대 만료는 시계를 바꾸지 않고 임대 칸을 과거로 돌려 만든다.
 */
@AutoConfigureMockMvc
@TestPropertySource(
    properties = {
      "app.processor.token=" + ProcessorJobApiTest.PROCESSOR_TOKEN,
      "app.analysis.processor.enabled=true"
    })
class ProcessorJobApiTest extends AnalysisIntegrationTest {

  static final String PROCESSOR_TOKEN = "test-processor-token";
  private static final String JOBS = "/v1/internal/processor/jobs";

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobRepository jobs;
  @Autowired private AnalysisJobStore store;
  @MockitoBean private AnalysisJobNotifier notifier;

  private UUID waitingJob(String youtubeVideoId) {
    return service
        .register(
            new AnalysisJobRequest(
                youtubeVideoId, "videos/" + youtubeVideoId + "/source.mp4", "제목", "채널", 600))
        .jobId();
  }

  private ResultActions claim() throws Exception {
    return mockMvc.perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN));
  }

  private ResultActions notice(UUID jobId, String action, Object body) throws Exception {
    return mockMvc.perform(
        post(JOBS + "/" + jobId + "/" + action)
            .header("X-Processor-Token", PROCESSOR_TOKEN)
            .contentType(MediaType.APPLICATION_JSON)
            .content(JsonMapper.builder().build().writeValueAsString(body)));
  }

  private void expireLease(UUID jobId) {
    jdbc.update(
        "update analysis_jobs set processor_lease_until = now() - interval '1 second' where id = ?",
        jobId);
  }

  private static String prefix(String youtubeVideoId, UUID jobId) {
    return "videos/" + youtubeVideoId + "/jobs/" + jobId;
  }

  // ---------- claim ----------

  @Test
  void claimGivesTheOldestWaitingJobWithALease() throws Exception {
    claim().andExpect(status().isNoContent());
    UUID first = waitingJob("claimFirst1");
    UUID second = waitingJob("claimSecnd1");

    claim()
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.jobId").value(first.toString()))
        .andExpect(jsonPath("$.youtubeVideoId").value("claimFirst1"))
        .andExpect(jsonPath("$.youtubeUrl").value("https://www.youtube.com/watch?v=claimFirst1"))
        .andExpect(jsonPath("$.s3Prefix").value(prefix("claimFirst1", first)))
        .andExpect(jsonPath("$.leaseSeconds").value(900));
    claim().andExpect(status().isOk()).andExpect(jsonPath("$.jobId").value(second.toString()));
    claim().andExpect(status().isNoContent());

    AnalysisJob job = jobs.findById(first).orElseThrow();
    assertThat(job.getStatus().name()).isEqualTo("RUNNING");
    assertThat(job.getProgressStage().name()).isEqualTo("LOADING_VIDEO");
    assertThat(job.getStartedAt()).isNotNull();
    assertThat(job.getProcessorClaims()).isEqualTo(1);
    assertThat(job.getProcessorLeaseUntil()).isNotNull();
    verify(notifier, atLeastOnce()).changed(first);
  }

  @Test
  void expiredLeaseIsGivenAgainThenFailsAfterTheLastClaim() throws Exception {
    UUID jobId = waitingJob("leaseExpir1");
    claim().andExpect(status().isOk());
    claim().andExpect(status().isNoContent());

    expireLease(jobId);
    claim().andExpect(status().isOk()).andExpect(jsonPath("$.jobId").value(jobId.toString()));
    assertThat(jobs.findById(jobId).orElseThrow().getProcessorClaims()).isEqualTo(2);

    expireLease(jobId);
    UUID next = waitingJob("leaseNext01");
    claim().andExpect(status().isOk()).andExpect(jsonPath("$.jobId").value(next.toString()));

    AnalysisJob failed = jobs.findById(jobId).orElseThrow();
    assertThat(failed.getStatus().name()).isEqualTo("FAILED");
    assertThat(failed.getFailureCode()).isEqualTo("PROCESSOR_TIMEOUT");
    assertThat(failed.isRetryable()).isTrue();
    assertThat(failed.getProcessorLeaseUntil()).isNull();
  }

  // ---------- 인증 ----------

  @Test
  void processorAndInternalTokensAreSeparate() throws Exception {
    mockMvc.perform(post(JOBS + "/claim")).andExpect(status().isUnauthorized());
    mockMvc
        .perform(post(JOBS + "/claim").header("X-Processor-Token", "wrong"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    mockMvc
        .perform(post(JOBS + "/claim").header("X-Internal-Token", TOKEN))
        .andExpect(status().isUnauthorized());
    // 다른 내부 API(카탈로그)는 노트북 토큰으로 열리지 않는다
    mockMvc
        .perform(get("/v1/internal/catalog/quality").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isUnauthorized());
    mockMvc
        .perform(get("/v1/internal/catalog/quality").header("X-Internal-Token", TOKEN))
        .andExpect(status().isOk());
  }

  // ---------- complete ----------

  @Test
  void completeRecordsTheRequestKeyOnce() throws Exception {
    UUID jobId = waitingJob("completeV01");
    String key = prefix("completeV01", jobId) + "/guide_job_request.json";

    notice(jobId, "complete", Map.of("guideJobRequestKey", key))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("PROCESSOR_JOB_CONFLICT"));

    claim().andExpect(status().isOk());
    notice(jobId, "complete", Map.of("guideJobRequestKey", key))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("guideJobRequestKey"));

    putObject(key);
    notice(jobId, "complete", Map.of("guideJobRequestKey", "videos/other/jobs/x/a.json"))
        .andExpect(status().isBadRequest());
    notice(jobId, "complete", Map.of("guideJobRequestKey", key)).andExpect(status().isAccepted());
    notice(jobId, "complete", Map.of("guideJobRequestKey", key)).andExpect(status().isAccepted());

    String otherKey = prefix("completeV01", jobId) + "/other.json";
    putObject(otherKey);
    notice(jobId, "complete", Map.of("guideJobRequestKey", otherKey))
        .andExpect(status().isConflict());

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getProcessorRequestKey()).isEqualTo(key);
    assertThat(job.getProcessorLeaseUntil()).isNull();
    assertThat(job.getProgressStage().name()).isEqualTo("BUILDING_GUIDE");
    assertThat(job.getStatus().name()).isEqualTo("RUNNING");

    // 끝났다고 알린 작업은 임대가 없어 다시 내주지 않는다
    claim().andExpect(status().isNoContent());
    notice(UUID.randomUUID(), "complete", Map.of("guideJobRequestKey", key))
        .andExpect(status().isNotFound());
  }

  // ---------- fail ----------

  @Test
  void failMapsTheProcessorCode() throws Exception {
    UUID rejected = waitingJob("failReject1");
    UUID unknown = waitingJob("failUnknwn1");
    claim().andExpect(status().isOk());
    claim().andExpect(status().isOk());

    notice(
            rejected,
            "fail",
            Map.of("code", "DOWNLOAD_REJECTED", "retryable", true, "message", "HTTP 403"))
        .andExpect(status().isNoContent());
    notice(rejected, "fail", Map.of("code", "DOWNLOAD_REJECTED")).andExpect(status().isNoContent());
    notice(unknown, "fail", Map.of("code", "SCHEMA_INVALID", "retryable", false, "message", "x"))
        .andExpect(status().isNoContent());
    notice(unknown, "fail", Map.of("message", "코드 없음")).andExpect(status().isBadRequest());

    AnalysisJob a = jobs.findById(rejected).orElseThrow();
    assertThat(a.getFailureCode()).isEqualTo("VIDEO_DOWNLOAD_REJECTED");
    assertThat(a.isRetryable()).as("BE 표가 정한다").isFalse();
    assertThat(a.getFailureMessage()).isEqualTo("[DOWNLOAD_REJECTED] HTTP 403");
    assertThat(a.getProgressStage().name()).isEqualTo("LOADING_VIDEO");
    AnalysisJob b = jobs.findById(unknown).orElseThrow();
    assertThat(b.getFailureCode()).isEqualTo("PROCESSOR_FAILED");
    assertThat(b.isRetryable()).as("모르는 코드는 노트북 값").isFalse();
  }

  // ---------- progress ----------

  @Test
  void progressMovesForwardOnlyAndExtendsTheLease() throws Exception {
    UUID jobId = waitingJob("progress001");
    notice(jobId, "progress", Map.of("stage", "SEGMENTING")).andExpect(status().isConflict());
    claim().andExpect(status().isOk());
    expireLease(jobId);

    notice(jobId, "progress", Map.of("stage", "SEGMENTING", "percent", 10))
        .andExpect(status().isNoContent());
    notice(jobId, "progress", Map.of("stage", "EXTRACTING_STEPS"))
        .andExpect(status().isNoContent());
    notice(jobId, "progress", Map.of("stage", "BUILDING_GUIDE"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("stage"));

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getProgressStage().name()).as("늦게 온 앞 단계는 무시").isEqualTo("SEGMENTING");
    assertThat(job.getProcessorLeaseUntil()).isAfter(java.time.Instant.now());
    // 임대가 늘어 다시 내주지 않는다
    claim().andExpect(status().isNoContent());
  }

  // ---------- worker ----------

  @Test
  void workerLeavesWaitingAndProcessorJobsAlone() throws Exception {
    UUID waiting = waitingJob("workerSkip1");
    assertThat(store.claimNext(WORK_ROOT)).as("연결 모드면 worker 는 대기 작업을 집지 않는다").isEmpty();

    claim().andExpect(status().isOk()).andExpect(jsonPath("$.jobId").value(waiting.toString()));
    UUID done = waitingJob("workerSkip2");
    claim().andExpect(status().isOk());
    String key = prefix("workerSkip2", done) + "/guide_job_request.json";
    putObject(key);
    notice(done, "complete", Map.of("guideJobRequestKey", key)).andExpect(status().isAccepted());

    assertThat(store.requeueRunning()).as("노트북 작업은 worker 재시작 복구에서 되돌리지 않는다").isZero();
    assertThat(jobs.findById(waiting).orElseThrow().getStatus().name()).isEqualTo("RUNNING");
    assertThat(jobs.findById(done).orElseThrow().getStatus().name()).isEqualTo("RUNNING");
  }
}
