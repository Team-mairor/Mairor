package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.users.support.AuthenticatedUser;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/**
 * 분석 재시도(API-VIDEO-006): 다시 돌리는 자리(대기열 · AI 단계), 권한, 재시도할 수 없는 작업, 시도 횟수 상한, 이미 재시도된 작업, 같은 영상의 다른
 * 진행 중 작업 합류, 하루 한도와 무관함을 PostgreSQL 로 확인한다. 하루 한도는 1 로 줄여 이미 다 쓴 회원도 재시도할 수 있는지 본다.
 */
@AutoConfigureMockMvc
@TestPropertySource(properties = "app.analysis.request.daily-limit-per-user=1")
class AnalysisRetryApiTest extends AnalysisIntegrationTest {

  private static final String PATH = "/v1/users/me/analysis-jobs";
  private static final String REQUEST_KEY = "videos/rtyAiStage1/jobs/x/guide_job_request.json";

  @Autowired private MockMvc mockMvc;

  private UUID userId;
  private UUID otherUserId;

  @BeforeEach
  void setUp() {
    userId = member();
    otherUserId = member();
  }

  @Test
  void jobStoppedBeforeTheNotebookFinishedGoesBackToTheQueue() throws Exception {
    UUID jobId =
        failedJob(video("rtyQueue001"), userId, "EXTRACTING_STEPS", "LLM_UNAVAILABLE", true);

    mockMvc
        .perform(retry(jobId).with(asMember(userId)))
        .andExpect(status().isAccepted())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.jobId").value(jobId.toString()))
        .andExpect(jsonPath("$.status").value("PENDING"))
        .andExpect(jsonPath("$.progressStage").value("QUEUED"))
        .andExpect(jsonPath("$.retryable").value(false))
        .andExpect(jsonPath("$.failureCode").value((Object) null))
        .andExpect(jsonPath("$.pollAfterSeconds").value(3));

    Map<String, Object> row =
        jdbc.queryForMap(
            "select attempt, failure_code, processor_claims, started_at from analysis_jobs where id = ?",
            jobId);
    assertThat(row.get("attempt")).isEqualTo(2);
    assertThat(row.get("failure_code")).isNull();
    assertThat(row.get("processor_claims")).isEqualTo(0);
    assertThat(row.get("started_at")).isNull();
  }

  @Test
  void jobStoppedAfterTheNotebookFinishedGoesBackToGuideBuilding() throws Exception {
    UUID jobId =
        failedJob(video("rtyAiStage1"), userId, "BUILDING_GUIDE", "ANALYSIS_TIMEOUT", true);
    jdbc.update(
        "update analysis_jobs set processor_request_key = ?, ai_job_id = 'ai-old',"
            + " ai_requested_at = now(), started_at = now() where id = ?",
        REQUEST_KEY,
        jobId);

    mockMvc
        .perform(retry(jobId).with(asMember(userId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.status").value("RUNNING"))
        .andExpect(jsonPath("$.progressStage").value("BUILDING_GUIDE"));

    Map<String, Object> row =
        jdbc.queryForMap(
            "select processor_request_key, ai_job_id, ai_requested_at from analysis_jobs where id = ?",
            jobId);
    assertThat(row.get("processor_request_key")).isEqualTo(REQUEST_KEY);
    assertThat(row.get("ai_job_id")).isNull();
    assertThat(row.get("ai_requested_at")).isNull();
  }

  @Test
  void joinedMemberCanRetryButAStrangerCannot() throws Exception {
    UUID jobId =
        failedJob(video("rtyAccess01"), otherUserId, "LOADING_VIDEO", "PROCESSOR_TIMEOUT", true);
    UUID stranger = member();
    joined(jobId, userId);

    mockMvc
        .perform(retry(jobId).with(asMember(stranger)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    mockMvc
        .perform(retry(UUID.randomUUID()).with(asMember(userId)))
        .andExpect(status().isNotFound());
    mockMvc
        .perform(retry(jobId).with(asMember(userId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.status").value("PENDING"));
  }

  @Test
  void completedOrNotRetryableJobsAreRefused() throws Exception {
    UUID notRetryable =
        failedJob(video("rtyNoRetry1"), userId, "EXTRACTING_STEPS", "NO_VALID_STEPS", false);
    UUID completed = job(video("rtyComplete"), userId, "COMPLETED", "DONE");

    for (UUID jobId : List.of(notRetryable, completed)) {
      mockMvc
          .perform(retry(jobId).with(asMember(userId)))
          .andExpect(status().isConflict())
          .andExpect(jsonPath("$.code").value("ANALYSIS_NOT_RETRYABLE"));
    }
    assertThat(
            jdbc.queryForObject(
                "select status || ':' || attempt from analysis_jobs where id = ?",
                String.class,
                notRetryable))
        .isEqualTo("FAILED:1");
  }

  @Test
  void jobThatUsedAllAttemptsShowsNotRetryableAndIsRefused() throws Exception {
    UUID jobId =
        failedJob(video("rtyMaxTry01"), userId, "LOADING_VIDEO", "PROCESSOR_TIMEOUT", true);
    jdbc.update("update analysis_jobs set attempt = 3 where id = ?", jobId);

    mockMvc
        .perform(get(PATH + "/" + jobId).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("FAILED"))
        .andExpect(jsonPath("$.retryable").value(false));
    mockMvc
        .perform(retry(jobId).with(asMember(userId)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("ANALYSIS_NOT_RETRYABLE"));
  }

  @Test
  void jobAlreadyRetriedBySomeoneElseIsReturnedAsItIs() throws Exception {
    UUID jobId =
        failedJob(video("rtyTwice001"), userId, "LOADING_VIDEO", "PROCESSOR_TIMEOUT", true);
    joined(jobId, otherUserId);
    mockMvc.perform(retry(jobId).with(asMember(otherUserId))).andExpect(status().isAccepted());

    mockMvc
        .perform(retry(jobId).with(asMember(userId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.jobId").value(jobId.toString()))
        .andExpect(jsonPath("$.status").value("PENDING"));

    assertThat(
            jdbc.queryForObject(
                "select attempt from analysis_jobs where id = ?", Integer.class, jobId))
        .isEqualTo(2);
  }

  @Test
  void jobStillOnItsFirstRunIsRefused() throws Exception {
    UUID jobId = job(video("rtyFirstRun"), userId, "RUNNING", "LOADING_VIDEO");

    mockMvc
        .perform(retry(jobId).with(asMember(userId)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("ANALYSIS_NOT_RETRYABLE"));
  }

  @Test
  void anotherActiveJobOfTheSameVideoIsJoinedInstead() throws Exception {
    UUID videoId = video("rtyOtherJob");
    UUID failed = failedJob(videoId, userId, "LOADING_VIDEO", "PROCESSOR_TIMEOUT", true);
    UUID active = job(videoId, otherUserId, "PENDING", "QUEUED");

    mockMvc
        .perform(retry(failed).with(asMember(userId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.jobId").value(active.toString()))
        .andExpect(jsonPath("$.status").value("PENDING"));

    mockMvc.perform(get(PATH + "/" + active).with(asMember(userId))).andExpect(status().isOk());
    assertThat(
            jdbc.queryForObject(
                "select status || ':' || attempt from analysis_jobs where id = ?",
                String.class,
                failed))
        .isEqualTo("FAILED:1");
    assertThat(
            jdbc.queryForObject(
                "select receipt_type from analysis_job_requests where analysis_job_id = ? and user_id = ?",
                String.class,
                active,
                userId))
        .isEqualTo("JOINED_JOB");
  }

  @Test
  void retryIsNotCountedAgainstTheDailyLimit() throws Exception {
    // 이 회원은 오늘 새 작업 1개(한도)를 이미 썼다: 실패한 그 작업
    UUID jobId =
        failedJob(video("rtyLimit001"), userId, "LOADING_VIDEO", "PROCESSOR_TIMEOUT", true);
    jdbc.update(
        "insert into analysis_job_requests (id, analysis_job_id, user_id, receipt_type, created_at)"
            + " values (?, ?, ?, 'NEW_JOB', now())",
        UUID.randomUUID(),
        jobId,
        userId);

    mockMvc.perform(retry(jobId).with(asMember(userId))).andExpect(status().isAccepted());
  }

  @Test
  void retryWithoutCsrfTokenIsRejected() throws Exception {
    UUID jobId =
        failedJob(video("rtyCsrf0001"), userId, "LOADING_VIDEO", "PROCESSOR_TIMEOUT", true);

    mockMvc
        .perform(post(PATH + "/" + jobId + "/retry").with(asMember(userId)))
        .andExpect(status().isForbidden());
    assertThat(
            jdbc.queryForObject(
                "select status from analysis_jobs where id = ?", String.class, jobId))
        .isEqualTo("FAILED");
  }

  // ---------- 도움 ----------

  private UUID member() {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
    return id;
  }

  private UUID video(String youtubeVideoId) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into videos (id, youtube_video_id, title, channel_title, duration_seconds, chapters,"
            + " meta_refreshed_at, created_at, updated_at) values (?, ?, '제목', '채널', 600, '[]'::jsonb,"
            + " now(), now(), now())",
        id,
        youtubeVideoId);
    return id;
  }

  private UUID job(UUID videoId, UUID requestedBy, String status, String stage) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, requested_by, attempt,"
            + " created_at, updated_at) values (?, ?, ?, ?, false, ?, 1, now(), now())",
        id,
        videoId,
        status,
        stage,
        requestedBy);
    return id;
  }

  private UUID failedJob(
      UUID videoId, UUID requestedBy, String stage, String failureCode, boolean retryable) {
    UUID id = job(videoId, requestedBy, "FAILED", stage);
    jdbc.update(
        "update analysis_jobs set failure_code = ?, failure_message = '실패', retryable = ?,"
            + " finished_at = now() where id = ?",
        failureCode,
        retryable,
        id);
    return id;
  }

  private void joined(UUID jobId, UUID memberId) {
    jdbc.update(
        "insert into analysis_job_requests (id, analysis_job_id, user_id, receipt_type, created_at)"
            + " values (?, ?, ?, 'JOINED_JOB', now())",
        UUID.randomUUID(),
        jobId,
        memberId);
  }

  private static MockHttpServletRequestBuilder retry(UUID jobId) {
    return post(PATH + "/" + jobId + "/retry").with(csrf());
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }
}
