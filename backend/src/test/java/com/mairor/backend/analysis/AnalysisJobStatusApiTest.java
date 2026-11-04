package com.mairor.backend.analysis;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.controller.AiCallbackController;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/**
 * 회원 분석 작업 상태 조회(API-VIDEO-003). 작업 상태는 SQL 로 바로 만든다(흐름은 {@code AiGuideJobFlowTest}·{@code
 * AiProgressFlowTest}). 로그인은 세션 없이 인증 정보만 붙인다.
 */
@AutoConfigureMockMvc
class AnalysisJobStatusApiTest extends AnalysisIntegrationTest {

  private static final String PATH = "/v1/users/me/analysis-jobs/";

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;

  private UUID owner;
  private UUID other;

  @BeforeEach
  void createMembers() {
    owner = member("owner");
    other = member("other");
  }

  @AfterEach
  void deleteMembers() {
    jdbc.update("delete from guides");
    jdbc.update("delete from analysis_jobs");
    jdbc.update("delete from users where id in (?, ?)", owner, other);
  }

  private UUID member(String name) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at)"
            + " values (?, ?, 'LOCAL', now(), now())",
        id,
        name + "-" + id + "@example.com");
    return id;
  }

  private static RequestPostProcessor as(UUID userId) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(userId, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }

  /** 회원이 요청한 작업. 상태·단계는 SQL 로 바꾼다. */
  private UUID jobOf(UUID requestedBy, String status, String stage) {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    "eFzG30avtOI", "videos/eFzG30avtOI/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set requested_by = ?, status = ?, progress_stage = ? where id = ?",
        requestedBy,
        status,
        stage,
        jobId);
    return jobId;
  }

  private void guide(UUID jobId, String reviewStatus) {
    store.saveGuideInput(jobId, "{\"videoId\": \"eFzG30avtOI\", \"steps\": []}");
    jdbc.update(
        "update guides set review_status = ? where analysis_job_id = ?", reviewStatus, jobId);
  }

  private String guideId(UUID jobId) {
    return jdbc.queryForObject(
        "select id::text from guides where analysis_job_id = ?", String.class, jobId);
  }

  private ResultActions fetch(UUID userId, UUID jobId) throws Exception {
    return mockMvc.perform(get(PATH + jobId).with(as(userId)));
  }

  @Test
  void runningJobShowsTheNumbersInsideTheCurrentStage() throws Exception {
    UUID jobId = jobOf(owner, "RUNNING", "BUILDING_GUIDE");
    guide(jobId, "NOT_READY");
    jdbc.update(
        "update analysis_jobs set ai_job_id = 'ai-1', ai_progress = ?::jsonb where id = ?",
        "{\"explanation\": {\"done\": 0, \"total\": 19}, \"frames\": {\"done\": 2000, \"total\":"
            + " 2000}, \"landmarks\": {\"done\": 840, \"total\": 2000}, \"area\": {\"done\": 0,"
            + " \"total\": 19}}",
        jobId);

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.jobId").value(jobId.toString()))
        .andExpect(jsonPath("$.status").value("RUNNING"))
        .andExpect(jsonPath("$.progressStage").value("BUILDING_GUIDE"))
        .andExpect(jsonPath("$.stageProgress.item").value("LANDMARKS"))
        .andExpect(jsonPath("$.stageProgress.done").value(840))
        .andExpect(jsonPath("$.stageProgress.total").value(2000))
        .andExpect(jsonPath("$.progressPercent").doesNotExist())
        .andExpect(jsonPath("$.estimatedRemainingSeconds").doesNotExist())
        .andExpect(jsonPath("$.reviewStatus").value("NOT_READY"))
        .andExpect(jsonPath("$.guideAvailable").value(false))
        .andExpect(jsonPath("$.guideId").doesNotExist())
        .andExpect(jsonPath("$.foundProducts", hasSize(0)))
        .andExpect(jsonPath("$.foundProductCount").value(0))
        .andExpect(jsonPath("$.pollAfterSeconds").value(3))
        .andExpect(jsonPath("$.completedAt").doesNotExist())
        .andExpect(jsonPath("$.createdAt").exists());
  }

  @Test
  void progressSentByTheAiShowsUpInTheStatus() throws Exception {
    UUID jobId = jobOf(owner, "RUNNING", "BUILDING_GUIDE");
    guide(jobId, "NOT_READY");
    jdbc.update("update analysis_jobs set ai_job_id = 'ai-e2e' where id = ?", jobId);

    mockMvc
        .perform(
            post(AiCallbackController.PROGRESS_PATH)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"jobId\": \"ai-e2e\", \"explanation\": {\"done\": 3, \"total\": 19},"
                        + " \"frames\": null, \"landmarks\": null, \"area\": null}"))
        .andExpect(status().isNoContent());

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.stageProgress.item").value("EXPLANATION"))
        .andExpect(jsonPath("$.stageProgress.done").value(3))
        .andExpect(jsonPath("$.stageProgress.total").value(19));
  }

  @Test
  void queuedJobWithoutAGuideIsNotReady() throws Exception {
    UUID jobId = jobOf(owner, "PENDING", "QUEUED");

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("PENDING"))
        .andExpect(jsonPath("$.stageProgress").doesNotExist())
        .andExpect(jsonPath("$.reviewStatus").value("NOT_READY"))
        .andExpect(jsonPath("$.pollAfterSeconds").value(3));
  }

  @Test
  void completedJobWaitingForReviewKeepsPolling() throws Exception {
    UUID jobId = jobOf(owner, "COMPLETED", "DONE");
    jdbc.update(
        "update analysis_jobs set progress_percent = 100, finished_at = now() where id = ?", jobId);
    guide(jobId, "PENDING");

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.progressPercent").value(100))
        .andExpect(jsonPath("$.stageProgress").doesNotExist())
        .andExpect(jsonPath("$.reviewStatus").value("PENDING"))
        .andExpect(jsonPath("$.guideAvailable").value(false))
        .andExpect(jsonPath("$.guideId").doesNotExist())
        .andExpect(jsonPath("$.pollAfterSeconds").value(3))
        .andExpect(jsonPath("$.completedAt").exists());
  }

  @Test
  void approvedGuideIsAvailableAndStopsPolling() throws Exception {
    UUID jobId = jobOf(owner, "COMPLETED", "DONE");
    guide(jobId, "APPROVED");

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.reviewStatus").value("APPROVED"))
        .andExpect(jsonPath("$.guideAvailable").value(true))
        .andExpect(jsonPath("$.guideId").value(guideId(jobId)))
        .andExpect(jsonPath("$.pollAfterSeconds").doesNotExist());
  }

  @Test
  void rejectedGuideStopsPolling() throws Exception {
    UUID jobId = jobOf(owner, "COMPLETED", "DONE");
    guide(jobId, "REJECTED");

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.reviewStatus").value("REJECTED"))
        .andExpect(jsonPath("$.guideAvailable").value(false))
        .andExpect(jsonPath("$.pollAfterSeconds").doesNotExist());
  }

  @Test
  void failedJobIs200WithTheReasonAndStopsPolling() throws Exception {
    UUID jobId = jobOf(owner, "FAILED", "BUILDING_GUIDE");
    jdbc.update(
        "update analysis_jobs set failure_code = 'ANALYSIS_TIMEOUT',"
            + " failure_message = '분석 시간이 초과되었습니다.', retryable = true,"
            + " finished_at = now() where id = ?",
        jobId);

    fetch(owner, jobId)
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("FAILED"))
        .andExpect(jsonPath("$.progressStage").value("BUILDING_GUIDE"))
        .andExpect(jsonPath("$.failureCode").value("ANALYSIS_TIMEOUT"))
        .andExpect(jsonPath("$.failureMessage").value("분석 시간이 초과되었습니다."))
        .andExpect(jsonPath("$.retryable").value(true))
        .andExpect(jsonPath("$.pollAfterSeconds").doesNotExist())
        .andExpect(jsonPath("$.completedAt").doesNotExist());
  }

  @Test
  void anotherMembersJobIsNotFound() throws Exception {
    UUID jobId = jobOf(owner, "RUNNING", "LOADING_VIDEO");

    fetch(other, jobId)
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }

  @Test
  void jobRegisteredByAnOperatorIsNotVisibleToMembers() throws Exception {
    UUID jobId = jobOf(null, "RUNNING", "LOADING_VIDEO");

    fetch(owner, jobId).andExpect(status().isNotFound());
  }

  @Test
  void unknownJobIsNotFound() throws Exception {
    fetch(owner, UUID.randomUUID()).andExpect(status().isNotFound());
  }

  @Test
  void loginIsRequired() throws Exception {
    UUID jobId = jobOf(owner, "RUNNING", "LOADING_VIDEO");

    mockMvc.perform(get(PATH + jobId)).andExpect(status().isUnauthorized());
  }
}
