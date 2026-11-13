package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AiFrameDelivery;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.service.AnalysisJobStatusView;
import com.mairor.backend.analysis.service.AnalysisRetryService;
import com.mairor.backend.analysis.service.ProcessorJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.analysis.worker.ProcessedJobSubmitter;
import com.mairor.backend.analysis.worker.WorkerProperties;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.external.ai.AiServerException;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageProperties;
import com.mairor.backend.guides.service.GuideReferenceLinkReconciliationDispatcher;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

/**
 * 노트북 흐름 전체(S15P31A306-358): 작업 등록 → 노트북 claim → 프레임 · 요청 JSON 업로드 → complete → worker 가 AI 에 맡김 →
 * AI 콜백 → 검수 대기. 노트북은 HTTP 호출과 저장소 파일로 흉내 내고 AI 는 가짜다. worker 스케줄러는 뜨지 않으므로 처리기를 직접 만들어 부른다.
 */
@AutoConfigureMockMvc
@TestPropertySource(
    properties = {
      "app.processor.token=" + ProcessorFlowTest.PROCESSOR_TOKEN,
      "app.analysis.processor.enabled=true"
    })
class ProcessorFlowTest extends AnalysisIntegrationTest {

  static final String PROCESSOR_TOKEN = "test-processor-token";
  private static final String JOBS = "/v1/internal/processor/jobs";
  private static final JsonMapper JSON = JsonMapper.builder().build();

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobRepository jobs;
  @Autowired private AnalysisJobStore store;
  @Autowired private ProcessorJobService processorJobs;
  @Autowired private ObjectStorage storage;
  @Autowired private StorageProperties storageProperties;
  @Autowired private AiProperties aiProperties;
  @Autowired private WorkerProperties workerProperties;
  @Autowired private ObjectMapper objectMapper;
  @Autowired private AiResultService aiResults;
  @Autowired private AnalysisRetryService retries;
  @MockitoBean private AiGuideJobClient ai;
  // AI 결과 반영 뒤 제품 링크 대조(-324)는 비동기라 다음 테스트의 표 정리와 겹칠 수 있다. 이 흐름과 무관해 가짜로 둔다
  @Autowired private AiFrameDelivery frameDelivery;
  @MockitoBean private GuideReferenceLinkReconciliationDispatcher linkReconciliation;

  private ProcessedJobSubmitter submitter;

  @BeforeEach
  void createSubmitter() {
    submitter =
        new ProcessedJobSubmitter(
            store,
            processorJobs,
            storage,
            storageProperties,
            ai,
            aiProperties,
            workerProperties,
            objectMapper,
            frameDelivery);
  }

  /** 노트북처럼 작업을 가져가 프레임 하나와 요청 JSON 을 올리고 complete 한다. */
  private UUID processedJob(String youtubeVideoId, String requestJson) throws Exception {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    youtubeVideoId, "videos/" + youtubeVideoId + "/source.mp4", "제목", "채널", 600))
            .jobId();
    mockMvc
        .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isOk());
    String prefix = "videos/" + youtubeVideoId + "/jobs/" + jobId;
    putObject(prefix + "/frames/step_01/frame_001680.jpg");
    String key = prefix + "/guide_job_request.json";
    write(key, requestJson.replace("{prefix}", prefix));
    mockMvc
        .perform(
            post(JOBS + "/" + jobId + "/complete")
                .header("X-Processor-Token", PROCESSOR_TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(JSON.writeValueAsString(Map.of("guideJobRequestKey", key))))
        .andExpect(status().isAccepted());
    return jobId;
  }

  private static String requestJson(String youtubeVideoId) {
    return "{\"callbackUrl\": \"https://api.mairor.com/api/v1/callbacks/guide-jobs/x\","
        + " \"guideInput\": {\"videoId\": \""
        + youtubeVideoId
        + "\", \"durationSeconds\": 600.0,"
        + " \"steps\": [{\"stepId\": \"s1\", \"order\": 1, \"startSeconds\": 10, \"endSeconds\": 40,"
        + " \"makeup\": \"eyeshadow\", \"eyeZone\": \"upperLid\", \"partLabel\": \"윗눈두덩이\","
        + " \"summary\": \"섀도를 바른다\", \"facts\": {\"area\": {\"value\": \"윗눈두덩\", \"source\": \"voice\"}}}]},"
        + " \"frames\": {\"source\": {\"width\": 1920, \"height\": 1080, \"fps\": 60}, \"items\": ["
        + "{\"frameIndex\": 1680, \"timestampMs\": 28000, \"stepId\": \"s1\", \"width\": 1920, \"height\": 1080,"
        + " \"url\": \"https://unsigned.example/x.jpg\","
        + " \"key\": \"{prefix}/frames/step_01/frame_001680.jpg\"}]}}";
  }

  private static void write(String key, String content) throws IOException {
    Path file = STORAGE_ROOT.resolve(key);
    Files.createDirectories(file.getParent());
    Files.writeString(file, content, StandardCharsets.UTF_8);
  }

  @Test
  void processedJobIsHandedToTheAiAndReachesReview() throws Exception {
    UUID jobId = processedJob("procFlow001", requestJson("procFlow001"));
    when(ai.submit(any())).thenReturn("ai-proc-1");

    assertThat(submitter.submitNext()).isTrue();
    assertThat(submitter.submitNext()).as("한 번만 맡긴다").isFalse();

    ArgumentCaptor<String> body = ArgumentCaptor.forClass(String.class);
    verify(ai).submit(body.capture());
    JsonNode sent = JSON.readTree(body.getValue());
    assertThat(sent.path("callbackUrl").asString())
        .isEqualTo(aiProperties.callbackBaseUrl() + "/v1/internal/ai/guide-jobs/callback");
    assertThat(sent.path("progressUrl").asString())
        .isEqualTo(aiProperties.callbackBaseUrl() + "/v1/internal/ai/guide-jobs/progress");
    JsonNode frame = sent.path("frames").path("items").get(0);
    assertThat(frame.path("url").asString()).startsWith("file:").endsWith("frame_001680.jpg");
    assertThat(frame.has("key")).isFalse();
    assertThat(sent.path("guideInput").path("steps").get(0).path("eyeZone").asString())
        .isEqualTo("upperLid");

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getAiJobId()).isEqualTo("ai-proc-1");
    assertThat(job.getStatus().name()).isEqualTo("RUNNING");
    assertThat(job.getProgressStage().name()).isEqualTo("BUILDING_GUIDE");
    assertThat(
            jdbc.queryForObject(
                "select (guide_input ->> 'videoId') || ':' || review_status || ':' || frames_manifest_key"
                    + " from guides where analysis_job_id = ?",
                String.class,
                jobId))
        .isEqualTo(
            "procFlow001:NOT_READY:videos/procFlow001/jobs/" + jobId + "/guide_job_request.json");

    aiResults.apply(
        new AiGuideJobCallbackRequest(
            "ai-proc-1",
            "procFlow001",
            "COMPLETED",
            JSON.readTree("{\"steps\": [{\"stepId\": \"s1\", \"order\": 1, \"actions\": []}]}"),
            JSON.readTree(
                "{\"videoId\": \"procFlow001\", \"meshVersion\": \"v1\", \"steps\": [{\"stepId\": \"s1\","
                    + " \"order\": 1, \"makeup\": \"eyeshadow\", \"subSteps\": []}]}"),
            null));
    assertThat(jobs.findById(jobId).orElseThrow().getStatus().name()).isEqualTo("COMPLETED");
    assertThat(
            jdbc.queryForObject(
                "select review_status from guides where analysis_job_id = ?", String.class, jobId))
        .as("AI 결과를 저장하면 검수 없이 바로 공개")
        .isEqualTo("APPROVED");
  }

  @Test
  void brokenRequestFailsWithoutCallingTheAi() throws Exception {
    UUID jobId = processedJob("procBroken1", requestJson("otherVideo1"));

    assertThat(submitter.submitNext()).isTrue();

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("PROCESSOR_OUTPUT_INVALID");
    assertThat(job.isRetryable()).isFalse();
    assertThat(job.getFailureMessage()).contains("otherVideo1");
    verify(ai, never()).submit(any());
  }

  @Test
  void aiRejectionFailsTheJob() throws Exception {
    UUID jobId = processedJob("procReject1", requestJson("procReject1"));
    when(ai.submit(any())).thenThrow(new AiServerException("400 VALIDATION_FAILED", 400, null));

    assertThat(submitter.submitNext()).isTrue();

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("AI_REQUEST_REJECTED");
    assertThat(job.getAiJobId()).isNull();
  }

  @Test
  void jobsNobodyPicksUpOrThatStalledTimeOut() throws Exception {
    UUID waiting =
        service
            .register(
                new AnalysisJobRequest(
                    "procWait001", "videos/procWait001/source.mp4", "제목", "채널", 600))
            .jobId();
    UUID fresh =
        service
            .register(
                new AnalysisJobRequest(
                    "procFresh01", "videos/procFresh01/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set created_at = now() - interval '31 minutes',"
            + " updated_at = now() - interval '31 minutes' where id = ?",
        waiting);
    assertThat(processorJobs.expireWaiting()).isEqualTo(1);
    AnalysisJob expired = jobs.findById(waiting).orElseThrow();
    assertThat(expired.getFailureCode()).isEqualTo("PROCESSOR_TIMEOUT");
    assertThat(expired.isRetryable()).isTrue();
    assertThat(expired.getProgressStage().name()).isEqualTo("QUEUED");
    assertThat(jobs.findById(fresh).orElseThrow().getStatus().name()).isEqualTo("PENDING");

    mockMvc
        .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isOk());
    // 임대가 끝난 지 31분: 마지막으로 만진 것은 임대를 받은 때(46분 전)다
    jdbc.update(
        "update analysis_jobs set processor_lease_until = now() - interval '31 minutes',"
            + " updated_at = now() - interval '46 minutes' where id = ?",
        fresh);
    assertThat(processorJobs.expireWaiting()).isEqualTo(1);
    AnalysisJob stalled = jobs.findById(fresh).orElseThrow();
    assertThat(stalled.getFailureCode()).isEqualTo("PROCESSOR_TIMEOUT");
    assertThat(stalled.getProgressStage().name()).isEqualTo("LOADING_VIDEO");
  }

  /** 노트북 응답 없음(S15P31A306-406): 5분 넘게 아무 작업도 안 만졌는데 그보다 오래 기다린 작업이 있으면 알린다. 시간 초과(30분)보다 먼저다. */
  @Test
  void aWaitingJobWithoutTheNotebookForFiveMinutesIsAStall() throws Exception {
    UUID waiting =
        service
            .register(
                new AnalysisJobRequest(
                    "procStlWait", "videos/procStlWait/source.mp4", "제목", "채널", 600))
            .jobId();
    service.register(
        new AnalysisJobRequest("procStlNew1", "videos/procStlNew1/source.mp4", "제목", "채널", 600));
    jdbc.update(
        "update analysis_jobs set created_at = now() - interval '6 minutes',"
            + " updated_at = now() - interval '6 minutes' where id = ?",
        waiting);

    ProcessorJobService.Stall stall = processorJobs.stalled().orElseThrow();
    assertThat(stall.waiting()).as("방금 들어온 작업은 아직 세지 않는다").isEqualTo(1);
    assertThat(stall.oldestWait()).isGreaterThanOrEqualTo(Duration.ofMinutes(6));
    assertThat(processorJobs.expireWaiting()).as("시간 초과는 아직").isZero();

    // 노트북이 작업을 가져가면(만지면) 응답 없음이 아니다
    mockMvc
        .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isOk());
    assertThat(processorJobs.stalled()).isEmpty();
  }

  /** 노트북은 한 번에 하나씩 처리한다. 앞 작업을 하는 동안 줄 선 작업은 기다리는 것이지 노트북이 꺼진 것이 아니다(S15P31A306-408). */
  @Test
  void waitingJobsDoNotTimeOutWhileTheNotebookIsWorking() throws Exception {
    // 노트북이 지금 처리 중인 작업
    UUID working =
        service
            .register(
                new AnalysisJobRequest(
                    "procWork001", "videos/procWork001/source.mp4", "제목", "채널", 600))
            .jobId();
    mockMvc
        .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isOk());
    // 예전에 가져갔다가 임대가 31분 전에 끝난 작업(마지막으로 만진 것은 46분 전)
    UUID stalled =
        service
            .register(
                new AnalysisJobRequest(
                    "procStall01", "videos/procStall01/source.mp4", "제목", "채널", 600))
            .jobId();
    String claimed =
        mockMvc
            .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat(claimed).contains(stalled.toString());
    jdbc.update(
        "update analysis_jobs set processor_lease_until = now() - interval '31 minutes',"
            + " updated_at = now() - interval '46 minutes' where id = ?",
        stalled);
    UUID queued =
        service
            .register(
                new AnalysisJobRequest(
                    "procQueue01", "videos/procQueue01/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set created_at = now() - interval '40 minutes',"
            + " updated_at = now() - interval '40 minutes' where id = ?",
        queued);

    // 노트북이 방금 작업을 가져갔으므로 줄 선 작업 · 임대가 지난 작업 모두 그대로 둔다
    assertThat(processorJobs.expireWaiting()).isZero();
    assertThat(jobs.findById(queued).orElseThrow().getStatus().name()).isEqualTo("PENDING");
    assertThat(jobs.findById(stalled).orElseThrow().getStatus().name()).isEqualTo("RUNNING");

    // 노트북이 31분 동안 아무 작업도 만지지 않으면 꺼진 것으로 본다. 임대가 남은 작업은 그대로다
    jdbc.update(
        "update analysis_jobs set updated_at = now() - interval '31 minutes' where id = ?",
        working);
    assertThat(processorJobs.expireWaiting()).isEqualTo(2);
    assertThat(jobs.findById(queued).orElseThrow().getFailureCode()).isEqualTo("PROCESSOR_TIMEOUT");
    assertThat(jobs.findById(stalled).orElseThrow().getFailureCode())
        .isEqualTo("PROCESSOR_TIMEOUT");
    assertThat(jobs.findById(working).orElseThrow().getStatus().name()).isEqualTo("RUNNING");
  }

  /** 재시도(API-VIDEO-006): 노트북 단계에서 멈춘 작업은 대기열로 돌아가 노트북이 다시 가져가고, 노트북 기다림 시간은 재시도한 때부터 센다. */
  @Test
  void jobRetriedBeforeTheNotebookFinishedIsClaimedAgainAndWaitsAnew() throws Exception {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    "procRetry01", "videos/procRetry01/source.mp4", "제목", "채널", 600))
            .jobId();
    mockMvc
        .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isOk());
    mockMvc
        .perform(
            post(JOBS + "/" + jobId + "/fail")
                .header("X-Processor-Token", PROCESSOR_TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"code\": \"STEP_EXTRACTION_FAILED\", \"retryable\": true, \"message\": \"503\"}"))
        .andExpect(status().isNoContent());
    // 처음 요청한 지 40분: 만든 시각으로 세면 재시도하자마자 노트북 기다림 시간 초과다
    jdbc.update(
        "update analysis_jobs set created_at = now() - interval '40 minutes',"
            + " updated_at = now() - interval '40 minutes' where id = ?",
        jobId);

    AnalysisJobStatusView retried = retries.retry(member(jobId), jobId);

    assertThat(retried.status().name()).isEqualTo("PENDING");
    assertThat(retried.progressStage().name()).isEqualTo("QUEUED");
    assertThat(processorJobs.expireWaiting()).as("재시도한 때부터 다시 기다린다").isZero();
    String claimed =
        mockMvc
            .perform(post(JOBS + "/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat(claimed).contains(jobId.toString());
    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getAttempt()).isEqualTo(2);
    assertThat(job.getProcessorClaims()).isEqualTo(1);
    assertThat(job.getProgressStage().name()).isEqualTo("LOADING_VIDEO");
  }

  /** 재시도(API-VIDEO-006): 노트북이 끝낸 뒤 AI 단계에서 멈춘 작업은 영상 처리를 되풀이하지 않고 같은 요청 JSON 으로 AI 에 다시 맡긴다. */
  @Test
  void jobRetriedAfterTheNotebookFinishedIsHandedToTheAiAgain() throws Exception {
    UUID jobId = processedJob("procRetryAi", requestJson("procRetryAi"));
    when(ai.submit(any())).thenReturn("ai-try-1", "ai-try-2");
    assertThat(submitter.submitNext()).isTrue();
    assertThat(aiResults.timeout("ai-try-1", "콜백이 오지 않음")).isTrue();

    AnalysisJobStatusView retried = retries.retry(member(jobId), jobId);

    assertThat(retried.status().name()).isEqualTo("RUNNING");
    assertThat(retried.progressStage().name()).isEqualTo("BUILDING_GUIDE");
    assertThat(submitter.submitNext()).isTrue();
    verify(ai, times(2)).submit(any());
    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getAiJobId()).isEqualTo("ai-try-2");
    assertThat(job.getAttempt()).isEqualTo(2);
    assertThat(job.getProcessorClaims()).as("노트북에 다시 내주지 않았다").isZero();
    assertThat(
            jdbc.queryForObject(
                "select count(*) from guides where analysis_job_id = ?", Integer.class, jobId))
        .isEqualTo(1);
  }

  /** 이 작업에 합류한 회원(재시도는 요청 · 합류한 회원만 할 수 있다). */
  private UUID member(UUID jobId) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
    jdbc.update(
        "insert into analysis_job_requests (id, analysis_job_id, user_id, receipt_type, created_at)"
            + " values (?, ?, ?, 'JOINED_JOB', now())",
        UUID.randomUUID(),
        jobId,
        id);
    return id;
  }
}
