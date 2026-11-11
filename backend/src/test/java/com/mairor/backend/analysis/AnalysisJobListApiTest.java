package com.mairor.backend.analysis;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/**
 * 내 분석 목록(API-VIDEO-007). 작업 · 가이드 · 요청 기록은 SQL 로 바로 만든다. 로그인은 세션 없이 인증 정보만 붙인다.
 *
 * <p>owner 기준으로 한 줄씩 다른 경우를 둔다: 내가 새로 요청(검수 대기) · 다른 회원 작업에 합류(승인) · 진행 중 · 실패 · 반려 · 다른 회원만 요청 ·
 * 운영자 작업(요청 기록 없음).
 */
@AutoConfigureMockMvc
class AnalysisJobListApiTest extends AnalysisIntegrationTest {

  private static final String PATH = "/v1/users/me/analysis-jobs";
  private static final Instant NOW = Instant.now().truncatedTo(ChronoUnit.SECONDS);

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;

  private UUID owner;
  private UUID other;
  private UUID newcomer;

  @BeforeEach
  void createMembers() {
    owner = member("owner");
    other = member("other");
    newcomer = member("newcomer");
  }

  @AfterEach
  void deleteMembers() {
    jdbc.update("delete from guides");
    jdbc.update("delete from analysis_jobs");
    jdbc.update("delete from users where id in (?, ?, ?)", owner, other, newcomer);
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

  /** 영상마다 작업 하나. 상태는 SQL 로 바꾸고, 가이드가 있으면 검수 상태를 정한다. */
  private UUID job(String youtubeVideoId, String status, String reviewStatus) {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    youtubeVideoId,
                    "videos/" + youtubeVideoId + "/source.mp4",
                    "제목 " + youtubeVideoId,
                    "채널",
                    600))
            .jobId();
    jdbc.update("update analysis_jobs set status = ? where id = ?", status, jobId);
    if (reviewStatus != null) {
      store.saveGuideInput(jobId, "{\"videoId\": \"" + youtubeVideoId + "\", \"steps\": []}");
      jdbc.update(
          "update guides set review_status = ?, reviewed_at = ? where analysis_job_id = ?",
          reviewStatus,
          "APPROVED".equals(reviewStatus) || "REJECTED".equals(reviewStatus)
              ? Timestamp.from(NOW)
              : null,
          jobId);
    }
    return jobId;
  }

  /** 회원이 그 작업을 요청(NEW_JOB)하거나 합류(JOINED_JOB)한 기록. */
  private void requested(UUID jobId, UUID userId, String receiptType, Instant at) {
    jdbc.update(
        "insert into analysis_job_requests (id, analysis_job_id, user_id, receipt_type, created_at)"
            + " values (?, ?, ?, ?, ?)",
        UUID.randomUUID(),
        jobId,
        userId,
        receiptType,
        Timestamp.from(at));
  }

  private String guideId(UUID jobId) {
    return jdbc.queryForObject(
        "select id::text from guides where analysis_job_id = ?", String.class, jobId);
  }

  private record Jobs(UUID mine, UUID joined, UUID rejected) {}

  private Jobs ownerJobs() {
    UUID mine = job("listMine001", "COMPLETED", "PENDING");
    requested(mine, owner, "NEW_JOB", NOW.minus(2, ChronoUnit.HOURS));

    UUID joined = job("listJoined1", "COMPLETED", "APPROVED");
    requested(joined, other, "NEW_JOB", NOW.minus(3, ChronoUnit.HOURS));
    requested(joined, owner, "JOINED_JOB", NOW.minus(1, ChronoUnit.HOURS));

    UUID running = job("listRunning", "RUNNING", "NOT_READY");
    requested(running, owner, "NEW_JOB", NOW.minus(10, ChronoUnit.MINUTES));

    UUID failed = job("listFailed1", "FAILED", null);
    requested(failed, owner, "NEW_JOB", NOW.minus(20, ChronoUnit.MINUTES));

    UUID rejected = job("listReject1", "COMPLETED", "REJECTED");
    requested(rejected, owner, "NEW_JOB", NOW.minus(30, ChronoUnit.MINUTES));

    UUID othersOnly = job("listOthers1", "COMPLETED", "PENDING");
    requested(othersOnly, other, "NEW_JOB", NOW.minus(5, ChronoUnit.MINUTES));

    job("listOperatr", "COMPLETED", "PENDING");
    return new Jobs(mine, joined, rejected);
  }

  private static MockHttpServletRequestBuilder list() {
    return get(PATH);
  }

  @Test
  void completedJobsTheMemberRequestedOrJoinedComeNewestFirst() throws Exception {
    Jobs jobs = ownerJobs();

    mockMvc
        .perform(list().with(as(owner)))
        .andExpect(status().isOk())
        .andExpect(header().string("Cache-Control", "no-store"))
        .andExpect(jsonPath("$.items", hasSize(2)))
        .andExpect(jsonPath("$.items[0].jobId").value(jobs.joined().toString()))
        .andExpect(jsonPath("$.items[0].youtubeVideoId").value("listJoined1"))
        .andExpect(jsonPath("$.items[0].title").value("제목 listJoined1"))
        .andExpect(jsonPath("$.items[0].status").value("COMPLETED"))
        .andExpect(jsonPath("$.items[0].reviewStatus").value("APPROVED"))
        .andExpect(jsonPath("$.items[0].guideId").value(guideId(jobs.joined())))
        .andExpect(
            jsonPath("$.items[0].requestedAt").value(NOW.minus(1, ChronoUnit.HOURS).toString()))
        .andExpect(jsonPath("$.items[0].reviewedAt").value(NOW.toString()))
        .andExpect(jsonPath("$.items[1].jobId").value(jobs.mine().toString()))
        .andExpect(jsonPath("$.items[1].reviewStatus").value("PENDING"))
        .andExpect(jsonPath("$.items[1].guideId").doesNotExist())
        .andExpect(jsonPath("$.items[1].reviewedAt").doesNotExist())
        .andExpect(jsonPath("$.items[1].videoId").exists())
        .andExpect(jsonPath("$.page").value(0))
        .andExpect(jsonPath("$.size").value(20))
        .andExpect(jsonPath("$.hasNext").value(false));
  }

  @Test
  void rejectedJobsShowOnlyWhenAskedFor() throws Exception {
    Jobs jobs = ownerJobs();

    mockMvc
        .perform(list().param("reviewStatus", "REJECTED").with(as(owner)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(1)))
        .andExpect(jsonPath("$.items[0].jobId").value(jobs.rejected().toString()))
        .andExpect(jsonPath("$.items[0].guideId").doesNotExist());

    mockMvc
        .perform(list().param("reviewStatus", "PENDING", "REJECTED").with(as(owner)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(2)))
        .andExpect(jsonPath("$.items[0].jobId").value(jobs.rejected().toString()))
        .andExpect(jsonPath("$.items[1].jobId").value(jobs.mine().toString()));

    mockMvc
        .perform(list().param("reviewStatus", "APPROVED,REJECTED").with(as(owner)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(2)));
  }

  @Test
  void pagesSayWhetherMoreItemsFollow() throws Exception {
    Jobs jobs = ownerJobs();

    mockMvc
        .perform(list().param("size", "1").with(as(owner)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(1)))
        .andExpect(jsonPath("$.items[0].jobId").value(jobs.joined().toString()))
        .andExpect(jsonPath("$.size").value(1))
        .andExpect(jsonPath("$.hasNext").value(true));

    mockMvc
        .perform(list().param("page", "1").param("size", "1").with(as(owner)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(1)))
        .andExpect(jsonPath("$.items[0].jobId").value(jobs.mine().toString()))
        .andExpect(jsonPath("$.page").value(1))
        .andExpect(jsonPath("$.hasNext").value(false));
  }

  @Test
  void theOtherMemberSeesOnlyTheirOwnRequests() throws Exception {
    Jobs jobs = ownerJobs();

    mockMvc
        .perform(list().with(as(other)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(2)))
        .andExpect(jsonPath("$.items[0].youtubeVideoId").value("listOthers1"))
        .andExpect(jsonPath("$.items[1].jobId").value(jobs.joined().toString()))
        .andExpect(
            jsonPath("$.items[1].requestedAt").value(NOW.minus(3, ChronoUnit.HOURS).toString()));
  }

  @Test
  void aMemberWithoutRequestsGetsAnEmptyPage() throws Exception {
    ownerJobs();

    mockMvc
        .perform(list().with(as(newcomer)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items", hasSize(0)))
        .andExpect(jsonPath("$.page").value(0))
        .andExpect(jsonPath("$.hasNext").value(false));
  }

  @Test
  void reviewStatusOutsideTheCardStatesIsRejected() throws Exception {
    mockMvc
        .perform(list().param("reviewStatus", "NOT_READY").with(as(owner)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("reviewStatus"));

    mockMvc
        .perform(list().param("reviewStatus", "DONE").with(as(owner)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void pageSizeAboveTheLimitIsRejected() throws Exception {
    mockMvc
        .perform(list().param("size", "101").with(as(owner)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void loginIsRequired() throws Exception {
    mockMvc.perform(list()).andExpect(status().isUnauthorized());
  }
}
