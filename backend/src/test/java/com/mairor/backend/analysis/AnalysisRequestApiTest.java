package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.analysis.service.AnalysisRequestReceipt;
import com.mairor.backend.analysis.service.AnalysisRequestService;
import com.mairor.backend.analysis.service.ReceiptType;
import com.mairor.backend.common.external.youtube.YouTubeClient;
import com.mairor.backend.common.external.youtube.YouTubeException;
import com.mairor.backend.common.external.youtube.YouTubeVideo;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/**
 * 회원 분석 요청(API-VIDEO-002): 재사용 · 합류 · 신규, 합류한 회원의 조회 권한, CC BY 재확인, 회원별 일일 한도, 동시 요청을 PostgreSQL 로
 * 확인한다. 한도는 테스트에서 2 로 줄인다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.analysis.request.daily-limit-per-user=2"
    })
@AutoConfigureMockMvc
class AnalysisRequestApiTest {

  private static final String PATH = "/v1/users/me/analysis-jobs";
  private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private AnalysisRequestService service;
  @MockitoBean private YouTubeClient youTube;

  private UUID userId;
  private UUID otherUserId;
  private String prefix;

  @BeforeEach
  void setUp() {
    userId = member();
    otherUserId = member();
    // 테스트마다 다른 영상 ID 를 써서 서로 섞이지 않게 한다(11자)
    prefix = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
  }

  // ---------- 접수 종류 ----------

  @Test
  void newJobIsCreatedAndRecordedForTheMember() throws Exception {
    UUID videoId = ccVideo("new");

    String jobId =
        jsonString(
            mockMvc
                .perform(request(videoId).with(asMember(userId)))
                .andExpect(status().isAccepted())
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.receiptType").value("NEW_JOB"))
                .andExpect(jsonPath("$.videoId").value(videoId.toString()))
                .andExpect(jsonPath("$.status").value("PENDING"))
                .andExpect(jsonPath("$.progressStage").value("QUEUED"))
                .andExpect(jsonPath("$.reviewStatus").value("NOT_READY"))
                .andExpect(jsonPath("$.guideId").value((Object) null))
                .andExpect(jsonPath("$.pollAfterSeconds").value(3)),
            "$.jobId");

    UUID job = UUID.fromString(jobId);
    assertThat(
            jdbc.queryForObject(
                "select requested_by from analysis_jobs where id = ?", UUID.class, job))
        .isEqualTo(userId);
    assertThat(
            jdbc.queryForObject(
                "select receipt_type from analysis_job_requests where analysis_job_id = ? and user_id = ?",
                String.class,
                job,
                userId))
        .isEqualTo("NEW_JOB");
    assertThat(
            jdbc.queryForObject(
                "select source_object_key from videos where id = ?", String.class, videoId))
        .isEqualTo("videos/" + yt("new") + "/source.mp4");

    mockMvc
        .perform(get(PATH + "/" + jobId).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.jobId").value(jobId));
  }

  @Test
  void secondMemberJoinsTheActiveJobAndCanSeeIt() throws Exception {
    UUID videoId = ccVideo("joi");
    String jobId =
        jsonString(
            mockMvc
                .perform(request(videoId).with(asMember(userId)))
                .andExpect(status().isAccepted()),
            "$.jobId");

    mockMvc
        .perform(get(PATH + "/" + jobId).with(asMember(otherUserId)))
        .andExpect(status().isNotFound());

    mockMvc
        .perform(request(videoId).with(asMember(otherUserId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.receiptType").value("JOINED_JOB"))
        .andExpect(jsonPath("$.jobId").value(jobId));

    mockMvc
        .perform(get(PATH + "/" + jobId).with(asMember(otherUserId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.jobId").value(jobId));
    // 영상 선택 응답의 내 진행 작업에도 보인다
    mockMvc
        .perform(
            post("/v1/videos")
                .with(csrf())
                .with(asMember(otherUserId))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"youtubeVideoId\": \"" + yt("joi") + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.analysisJobId").value(jobId));

    // 같은 회원이 다시 요청해도 합류이고 기록은 한 줄
    mockMvc
        .perform(request(videoId).with(asMember(otherUserId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.receiptType").value("JOINED_JOB"));
    assertThat(
            jdbc.queryForObject(
                "select count(*) from analysis_job_requests where analysis_job_id = ?",
                Integer.class,
                UUID.fromString(jobId)))
        .isEqualTo(2);
  }

  @Test
  void memberCanJoinAnOperatorJob() throws Exception {
    UUID videoId = ccVideo("opr");
    UUID operatorJob = insertJob(videoId, null, "RUNNING");

    mockMvc
        .perform(request(videoId).with(asMember(userId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.receiptType").value("JOINED_JOB"))
        .andExpect(jsonPath("$.jobId").value(operatorJob.toString()))
        .andExpect(jsonPath("$.status").value("RUNNING"));

    mockMvc
        .perform(get(PATH + "/" + operatorJob).with(asMember(userId)))
        .andExpect(status().isOk());
  }

  @Test
  void approvedGuideIsReusedWithoutJob() throws Exception {
    UUID videoId = ccVideo("reu");
    UUID guideId = insertApprovedGuide(videoId);

    mockMvc
        .perform(request(videoId).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.receiptType").value("REUSED_GUIDE"))
        .andExpect(jsonPath("$.jobId").value((Object) null))
        .andExpect(jsonPath("$.guideId").value(guideId.toString()))
        .andExpect(jsonPath("$.status").value("COMPLETED"))
        .andExpect(jsonPath("$.progressStage").value("DONE"))
        .andExpect(jsonPath("$.reviewStatus").value("APPROVED"))
        .andExpect(jsonPath("$.pollAfterSeconds").value((Object) null));

    assertThat(
            jdbc.queryForObject(
                "select count(*) from analysis_job_requests where user_id = ?",
                Integer.class,
                userId))
        .isZero();
  }

  // ---------- 영상 확인 ----------

  @Test
  void videoMustExistAndStillBeCreativeCommons() throws Exception {
    mockMvc
        .perform(request(UUID.randomUUID()).with(asMember(userId)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    UUID notCc = insertVideo(yt("ncc"));
    when(youTube.videos(List.of(yt("ncc"))))
        .thenReturn(List.of(video(yt("ncc"), "youtube", "public")));
    mockMvc
        .perform(request(notCc).with(asMember(userId)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("VIDEO_UNSUPPORTED_FOR_ANALYSIS"));

    // 승인 가이드가 있어도 CC BY 가 아니게 됐으면 내주지 않는다
    UUID reused = insertVideo(yt("rnc"));
    insertApprovedGuide(reused);
    when(youTube.videos(List.of(yt("rnc"))))
        .thenReturn(List.of(video(yt("rnc"), "youtube", "public")));
    mockMvc.perform(request(reused).with(asMember(userId))).andExpect(status().isConflict());

    UUID gone = insertVideo(yt("gon"));
    when(youTube.videos(List.of(yt("gon")))).thenReturn(List.of());
    mockMvc
        .perform(request(gone).with(asMember(userId)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("VIDEO_UNSUPPORTED_FOR_ANALYSIS"));

    UUID quota = insertVideo(yt("quo"));
    when(youTube.videos(List.of(yt("quo"))))
        .thenThrow(new YouTubeException(YouTubeException.Kind.QUOTA_EXCEEDED, "quota", null));
    mockMvc
        .perform(request(quota).with(asMember(userId)))
        .andExpect(status().isServiceUnavailable())
        .andExpect(jsonPath("$.code").value("VIDEO_ANALYSIS_UNAVAILABLE"));

    assertThat(
            jdbc.queryForObject(
                "select count(*) from analysis_jobs where video_id in (?, ?, ?)",
                Integer.class,
                notCc,
                gone,
                quota))
        .isZero();
  }

  @Test
  void videoIdMustBeUuid() throws Exception {
    mockMvc
        .perform(
            post(PATH)
                .with(csrf())
                .with(asMember(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"videoId\": \"not-a-uuid\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("videoId"));
    mockMvc
        .perform(
            post(PATH)
                .with(csrf())
                .with(asMember(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
        .andExpect(status().isBadRequest());
    verify(youTube, never()).videos(org.mockito.ArgumentMatchers.anyList());
  }

  @Test
  void needsLoginAndCsrf() throws Exception {
    UUID videoId = UUID.randomUUID();
    mockMvc.perform(request(videoId)).andExpect(status().isUnauthorized());
    mockMvc
        .perform(
            post(PATH)
                .with(asMember(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"videoId\": \"" + videoId + "\"}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  // ---------- 일일 한도 ----------

  @Test
  void dailyLimitCountsOnlyNewJobs() throws Exception {
    // 합류 · 재사용은 세지 않는다
    UUID joined = ccVideo("lj0");
    insertJob(joined, null, "PENDING");
    mockMvc.perform(request(joined).with(asMember(userId))).andExpect(status().isAccepted());
    UUID reused = ccVideo("lr0");
    insertApprovedGuide(reused);
    mockMvc.perform(request(reused).with(asMember(userId))).andExpect(status().isOk());

    for (String suffix : List.of("l01", "l02")) {
      mockMvc
          .perform(request(ccVideo(suffix)).with(asMember(userId)))
          .andExpect(status().isAccepted())
          .andExpect(jsonPath("$.receiptType").value("NEW_JOB"));
    }

    Instant resetAt = LocalDate.now(SEOUL).plusDays(1).atStartOfDay(SEOUL).toInstant();
    UUID third = ccVideo("l03");
    mockMvc
        .perform(request(third).with(asMember(userId)))
        .andExpect(status().isTooManyRequests())
        .andExpect(jsonPath("$.code").value("ANALYSIS_DAILY_LIMIT_EXCEEDED"))
        .andExpect(jsonPath("$.resetAt").value(resetAt.toString()))
        .andExpect(header().exists("Retry-After"));
    assertThat(
            jdbc.queryForObject(
                "select count(*) from analysis_jobs where video_id = ?", Integer.class, third))
        .isZero();

    // 한도에 걸린 회원도 진행 중 작업 합류 · 재사용은 된다. 다른 회원은 따로 센다
    mockMvc.perform(request(joined).with(asMember(userId))).andExpect(status().isAccepted());
    mockMvc.perform(request(reused).with(asMember(userId))).andExpect(status().isOk());
    mockMvc
        .perform(request(third).with(asMember(otherUserId)))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.receiptType").value("NEW_JOB"));
  }

  @Test
  void otherErrorsHaveNoResetAt() throws Exception {
    mockMvc
        .perform(request(UUID.randomUUID()).with(asMember(userId)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.resetAt").doesNotExist());
  }

  // ---------- 동시 요청 ----------

  @Test
  void concurrentRequestsForOneVideoMakeOneJob() throws Exception {
    UUID videoId = ccVideo("cnc");
    List<UUID> members = new ArrayList<>();
    for (int i = 0; i < 4; i++) {
      members.add(member());
    }
    ExecutorService pool = Executors.newFixedThreadPool(members.size());
    CountDownLatch start = new CountDownLatch(1);
    try {
      List<Future<AnalysisRequestReceipt>> results = new ArrayList<>();
      for (UUID member : members) {
        results.add(
            pool.submit(
                () -> {
                  start.await();
                  return service.request(member, videoId.toString());
                }));
      }
      start.countDown();
      List<AnalysisRequestReceipt> receipts = new ArrayList<>();
      for (Future<AnalysisRequestReceipt> result : results) {
        receipts.add(result.get(30, TimeUnit.SECONDS));
      }
      assertThat(receipts)
          .extracting(AnalysisRequestReceipt::jobId)
          .containsOnly(receipts.getFirst().jobId());
      assertThat(receipts).filteredOn(r -> r.receiptType() == ReceiptType.NEW_JOB).hasSize(1);
    } finally {
      pool.shutdownNow();
    }
    assertThat(
            jdbc.queryForObject(
                "select count(*) from analysis_jobs where video_id = ?", Integer.class, videoId))
        .isEqualTo(1);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from analysis_job_requests r join analysis_jobs j on j.id = r.analysis_job_id"
                    + " where j.video_id = ?",
                Integer.class,
                videoId))
        .isEqualTo(members.size());
  }

  // ---------- 도움 ----------

  private String yt(String suffix) {
    return prefix + suffix;
  }

  private UUID member() {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
    return id;
  }

  /** 저장된 영상 + YouTube 가 CC BY 공개 영상으로 답하게 한다. */
  private UUID ccVideo(String suffix) {
    String id = yt(suffix);
    UUID videoId = insertVideo(id);
    when(youTube.videos(List.of(id))).thenReturn(List.of(video(id, "creativeCommon", "public")));
    return videoId;
  }

  private static YouTubeVideo video(String id, String license, String privacy) {
    return new YouTubeVideo(
        id,
        "제목 " + id,
        "채널",
        "",
        600,
        "https://i.ytimg.com/vi/" + id + "/hqdefault.jpg",
        1000L,
        Instant.parse("2026-10-01T09:00:00Z"),
        privacy,
        license,
        false,
        "none");
  }

  private static MockHttpServletRequestBuilder request(UUID videoId) {
    return post(PATH)
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"videoId\": \"" + videoId + "\"}");
  }

  private UUID insertVideo(String youtubeVideoId) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into videos (id, youtube_video_id, title, channel_title, duration_seconds, chapters,"
            + " meta_refreshed_at, created_at, updated_at) values (?, ?, '저장된 제목', '채널', 600, '[]'::jsonb,"
            + " now(), now(), now())",
        id,
        youtubeVideoId);
    return id;
  }

  private UUID insertJob(UUID videoId, UUID requestedBy, String status) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into analysis_jobs (id, video_id, status, progress_stage, retryable, requested_by, attempt,"
            + " created_at, updated_at) values (?, ?, ?, 'QUEUED', false, ?, 1, now(), now())",
        id,
        videoId,
        status,
        requestedBy);
    return id;
  }

  private UUID insertApprovedGuide(UUID videoId) {
    UUID jobId = insertJob(videoId, null, "COMPLETED");
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into guides (id, video_id, analysis_job_id, version, review_status, guide_input,"
            + " created_at, updated_at) values (?, ?, ?, 1, 'APPROVED', '{}'::jsonb, now(), now())",
        id,
        videoId,
        jobId);
    return id;
  }

  private static String jsonString(
      org.springframework.test.web.servlet.ResultActions actions, String path) throws Exception {
    return com.jayway.jsonpath.JsonPath.read(
        actions.andReturn().getResponse().getContentAsString(), path);
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }
}
