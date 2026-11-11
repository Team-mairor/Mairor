package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
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
        .isEqualTo("PENDING");
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
        "update analysis_jobs set created_at = now() - interval '31 minutes' where id = ?",
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
    jdbc.update(
        "update analysis_jobs set processor_lease_until = now() - interval '31 minutes' where id = ?",
        fresh);
    assertThat(processorJobs.expireWaiting()).isEqualTo(1);
    AnalysisJob stalled = jobs.findById(fresh).orElseThrow();
    assertThat(stalled.getFailureCode()).isEqualTo("PROCESSOR_TIMEOUT");
    assertThat(stalled.getProgressStage().name()).isEqualTo("LOADING_VIDEO");
  }
}
