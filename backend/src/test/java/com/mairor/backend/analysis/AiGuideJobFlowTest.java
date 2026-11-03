package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.common.security.InternalTokenFilter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.json.JsonMapper;

/**
 * AI 콜백 → 가이드 저장 → 운영자 검수, 그리고 콜백이 오지 않은 작업의 시간 초과. 작업은 AI 에 맡긴 상태(RUNNING · BUILDING_GUIDE ·
 * {@code ai_job_id})로 바로 만들어 둔다(앞 단계는 {@code AnalysisWorkerFlowTest}).
 */
@AutoConfigureMockMvc
class AiGuideJobFlowTest extends AnalysisIntegrationTest {

  private static final String CALLBACK = "/v1/internal/ai/guide-jobs/callback";
  private static final String GUIDES = "/v1/internal/guides";

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;
  @Autowired private AnalysisJobRepository jobs;
  @Autowired private AiResultService aiResults;

  private String completedCallback;

  @BeforeEach
  void loadFixture() throws IOException {
    // ai/samples/local_01 의 가이드 영역(19단계)에 단계마다 동작 하나를 붙인 COMPLETED 콜백
    completedCallback =
        new ClassPathResource("analysis/ai-callback-completed.json")
            .getContentAsString(StandardCharsets.UTF_8);
  }

  /** AI 에 맡긴 작업을 만든다: 작업 RUNNING · BUILDING_GUIDE · ai_job_id, 가이드는 입력만 있는 NOT_READY. */
  private UUID awaitingJob(String youtubeVideoId, String aiJobId) {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    youtubeVideoId, "videos/" + youtubeVideoId + "/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set status = 'RUNNING', progress_stage = 'BUILDING_GUIDE',"
            + " started_at = now(), ai_job_id = ? where id = ?",
        aiJobId,
        jobId);
    store.saveGuideInput(jobId, "{\"videoId\": \"" + youtubeVideoId + "\", \"steps\": []}");
    return jobId;
  }

  private String callbackFor(String aiJobId) {
    return completedCallback.replace("8728c83b0d124c74a23863a50d4d7c0c", aiJobId);
  }

  private String guideIdOf(UUID jobId) {
    return jdbc.queryForObject(
        "select id::text from guides where analysis_job_id = ?", String.class, jobId);
  }

  @Test
  void callbackFixtureMatchesTheSharedSchema() {
    assertThat(GuideJobSchemas.callbackViolations(completedCallback)).isEmpty();
  }

  @Test
  void completedCallbackStoresTheGuideAndWaitsForReview() throws Exception {
    UUID jobId = awaitingJob("eFzG30avtOI", "ai-done-1");

    mockMvc
        .perform(
            post(CALLBACK)
                .contentType(MediaType.APPLICATION_JSON)
                .content(callbackFor("ai-done-1")))
        .andExpect(status().isNoContent());

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.COMPLETED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.DONE);
    assertThat(
            jdbc.queryForObject(
                "select review_status || ':' || mesh_version || ':'"
                    + " || jsonb_array_length(explanation -> 'steps') || ':'"
                    + " || jsonb_array_length(area -> 'steps')"
                    + " from guides where analysis_job_id = ?",
                String.class,
                jobId))
        .isEqualTo("PENDING:v1:19:19");

    mockMvc
        .perform(
            get("/v1/internal/analysis-jobs/" + jobId).header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.aiJobId").value("ai-done-1"))
        .andExpect(jsonPath("$.guideId").value(guideIdOf(jobId)));
  }

  @Test
  void theSameCallbackAgainChangesNothing() throws Exception {
    UUID jobId = awaitingJob("eFzG30avtOI", "ai-twice-1");
    mockMvc
        .perform(
            post(CALLBACK)
                .contentType(MediaType.APPLICATION_JSON)
                .content(callbackFor("ai-twice-1")))
        .andExpect(status().isNoContent());
    mockMvc
        .perform(
            post(GUIDES + "/" + guideIdOf(jobId) + "/review")
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\": \"APPROVED\"}"))
        .andExpect(status().isOk());

    mockMvc
        .perform(
            post(CALLBACK)
                .contentType(MediaType.APPLICATION_JSON)
                .content(callbackFor("ai-twice-1")))
        .andExpect(status().isNoContent());

    assertThat(
            jdbc.queryForObject(
                "select review_status from guides where analysis_job_id = ?", String.class, jobId))
        .as("재전송된 콜백이 승인을 되돌리지 않는다")
        .isEqualTo("APPROVED");
  }

  @Test
  void failedCallbackFailsTheJobAsRetryable() throws Exception {
    UUID jobId = awaitingJob("failedVid01", "ai-failed-1");

    mockMvc
        .perform(
            post(CALLBACK)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"jobId": "ai-failed-1", "videoId": "failedVid01", "status": "FAILED",
                     "guide": null, "area": null,
                     "error": {"code": "GENERATION_FAILED", "message": "설명을 받지 못한 단계가 있습니다",
                               "details": [{"field": "steps.3", "reason": "timeout"}]}}
                    """))
        .andExpect(status().isNoContent());

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.FAILED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.BUILDING_GUIDE);
    assertThat(job.getFailureCode()).isEqualTo("AI_GENERATION_FAILED");
    assertThat(job.getFailureMessage()).isEqualTo("설명을 받지 못한 단계가 있습니다");
    assertThat(job.isRetryable()).isTrue();
    assertThat(
            jdbc.queryForObject(
                "select review_status from guides where analysis_job_id = ?", String.class, jobId))
        .isEqualTo("NOT_READY");
  }

  @Test
  void unknownJobIs404AndBrokenBodyIs400WithoutAnyToken() throws Exception {
    mockMvc
        .perform(
            post(CALLBACK)
                .contentType(MediaType.APPLICATION_JSON)
                .content(callbackFor("ai-nobody")))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    mockMvc
        .perform(
            post(CALLBACK)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"jobId\": \"ai-x\", \"videoId\": \"v\", \"status\": \"RUNNING\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void reviewApprovesOnceAndNeedsTheToken() throws Exception {
    UUID jobId = awaitingJob("reviewVid01", "ai-review-1");
    aiResults.apply(callbackRequest("ai-review-1"));
    String guideId = guideIdOf(jobId);

    mockMvc
        .perform(get(GUIDES + "/" + guideId).header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.reviewStatus").value("PENDING"))
        .andExpect(jsonPath("$.explanation.steps.length()").value(19))
        .andExpect(jsonPath("$.area.meshVersion").value("v1"))
        .andExpect(jsonPath("$.guideInput.videoId").value("reviewVid01"));
    mockMvc
        .perform(
            post(GUIDES + "/" + guideId + "/review")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\": \"APPROVED\"}"))
        .andExpect(status().isUnauthorized());

    mockMvc
        .perform(
            post(GUIDES + "/" + guideId + "/review")
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\": \"APPROVED\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.reviewStatus").value("APPROVED"))
        .andExpect(jsonPath("$.reviewedAt").isNotEmpty());
    mockMvc
        .perform(
            post(GUIDES + "/" + guideId + "/review")
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\": \"REJECTED\"}"))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("CONFLICT"));
    mockMvc
        .perform(
            post(GUIDES + "/" + UUID.randomUUID() + "/review")
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\": \"APPROVED\"}"))
        .andExpect(status().isNotFound());
  }

  @Test
  void approvingANewVersionTakesTheOldOneDown() throws Exception {
    UUID first = awaitingJob("twoVersion1", "ai-v1");
    aiResults.apply(callbackRequest("ai-v1"));
    review(guideIdOf(first), "APPROVED");
    UUID second = awaitingJob("twoVersion1", "ai-v2");
    aiResults.apply(callbackRequest("ai-v2"));

    review(guideIdOf(second), "APPROVED");

    assertThat(
            jdbc.queryForObject(
                "select string_agg(version || ':' || review_status, ',' order by version)"
                    + " from guides g join videos v on v.id = g.video_id"
                    + " where v.youtube_video_id = 'twoVersion1'",
                String.class))
        .isEqualTo("1:REJECTED,2:APPROVED");
  }

  @Test
  void timeoutFailsOnlyAJobStillWaitingForTheAi() {
    UUID jobId = awaitingJob("timeoutVid1", "ai-slow-1");

    assertThat(aiResults.timeout("ai-slow-1", "AI 서버에 작업이 없습니다")).isTrue();
    assertThat(aiResults.timeout("ai-slow-1", "두 번째")).as("이미 끝난 작업").isFalse();

    AnalysisJob job = jobs.findById(jobId).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("ANALYSIS_TIMEOUT");
    assertThat(job.isRetryable()).isTrue();
  }

  private AiGuideJobCallbackRequest callbackRequest(String aiJobId) {
    return JsonMapper.builder()
        .build()
        .readValue(callbackFor(aiJobId), AiGuideJobCallbackRequest.class);
  }

  private void review(String guideId, String decision) throws Exception {
    mockMvc
        .perform(
            post(GUIDES + "/" + guideId + "/review")
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"decision\": \"" + decision + "\"}"))
        .andExpect(status().isOk());
  }
}
