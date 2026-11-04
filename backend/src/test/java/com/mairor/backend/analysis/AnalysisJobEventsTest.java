package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.sse.PgNotificationListener;
import com.mairor.backend.analysis.sse.SseHub;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 분석 상태 SSE. 상태는 SQL 로 바꾸고 {@link AnalysisJobNotifier}로 알린다. 알림은 실제 LISTEN 연결({@link
 * PgNotificationListener})로 돌아와 열린 연결에 간다. 상태를 바꾸는 연결과 SSE 를 가진 쪽이 다른 프로세스인 운영과 같은 길이다.
 */
@AutoConfigureMockMvc
class AnalysisJobEventsTest extends AnalysisIntegrationTest {

  private static final String PATH = "/v1/users/me/analysis-jobs/";
  private static final Duration WAIT = Duration.ofSeconds(10);
  private static final Pattern DONE = Pattern.compile("\"done\":(\\d+)");

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;
  @Autowired private AnalysisJobNotifier notifier;
  @Autowired private PlatformTransactionManager transactionManager;
  @Autowired private SseHub hub;
  @Autowired private PgNotificationListener listener;

  private UUID owner;
  private UUID other;
  private final List<MvcResult> streams = new ArrayList<>();

  @BeforeEach
  void createMembers() {
    owner = member("owner");
    other = member("other");
  }

  @AfterEach
  void cleanUp() {
    hub.stop();
    hub.start();
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

  /** 회원이 요청한, AI 에 맡긴 작업(RUNNING · BUILDING_GUIDE). */
  private UUID runningJob() {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    "eFzG30avtOI", "videos/eFzG30avtOI/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set requested_by = ?, status = 'RUNNING',"
            + " progress_stage = 'BUILDING_GUIDE', ai_job_id = 'ai-sse' where id = ?",
        owner,
        jobId);
    store.saveGuideInput(jobId, "{\"videoId\": \"eFzG30avtOI\", \"steps\": []}");
    return jobId;
  }

  private MvcResult open(UUID jobId) throws Exception {
    MvcResult result =
        mockMvc
            .perform(
                get(PATH + jobId + "/events").with(as(owner)).accept(MediaType.TEXT_EVENT_STREAM))
            .andExpect(request().asyncStarted())
            .andReturn();
    streams.add(result);
    return result;
  }

  private static String body(MvcResult stream) throws Exception {
    return stream.getResponse().getContentAsString(StandardCharsets.UTF_8);
  }

  private static int events(MvcResult stream) throws Exception {
    return body(stream).split("event:" + SseHub.EVENT, -1).length - 1;
  }

  /** SQL 로 바꾸고 같은 트랜잭션에서 알린다(상태를 바꾸는 다른 프로세스 대신). */
  private void changeAndNotify(UUID jobId, String sql, Object... args) {
    new TransactionTemplate(transactionManager)
        .executeWithoutResult(
            status -> {
              jdbc.update(sql, args);
              notifier.changed(jobId);
            });
  }

  private static String progress(int done) {
    return "{\"explanation\": {\"done\": "
        + done
        + ", \"total\": 100}, \"frames\": null, \"landmarks\": null, \"area\": null}";
  }

  @Test
  void opensWithTheCurrentStateAndTheRightHeaders() throws Exception {
    UUID jobId = runningJob();

    MvcResult stream = open(jobId);

    assertThat(stream.getResponse().getContentType()).startsWith(MediaType.TEXT_EVENT_STREAM_VALUE);
    assertThat(stream.getResponse().getHeader("X-Accel-Buffering")).isEqualTo("no");
    assertThat(stream.getResponse().getHeader("Cache-Control")).isEqualTo("no-store");
    assertThat(body(stream))
        .contains("event:" + SseHub.EVENT)
        .contains("\"jobId\":\"" + jobId + "\"")
        .contains("\"status\":\"RUNNING\"")
        .contains("\"progressStage\":\"BUILDING_GUIDE\"");
    assertThat(events(stream)).isEqualTo(1);
    assertThat(hub.openConnections()).isEqualTo(1);
  }

  @Test
  void aChangeAnnouncedFromAnotherConnectionIsPushed() throws Exception {
    UUID jobId = runningJob();
    MvcResult stream = open(jobId);

    changeAndNotify(
        jobId, "update analysis_jobs set ai_progress = ?::jsonb where id = ?", progress(7), jobId);

    await()
        .atMost(WAIT)
        .untilAsserted(
            () ->
                assertThat(body(stream))
                    .contains("\"stageProgress\":{\"item\":\"EXPLANATION\",\"done\":7"));
    assertThat(events(stream)).isEqualTo(2);
  }

  @Test
  void anAnnouncementWithoutAVisibleChangeSendsNothing() throws Exception {
    UUID jobId = runningJob();
    MvcResult stream = open(jobId);

    changeAndNotify(jobId, "update analysis_jobs set updated_at = now() where id = ?", jobId);
    changeAndNotify(
        jobId, "update analysis_jobs set ai_progress = ?::jsonb where id = ?", progress(1), jobId);

    await().atMost(WAIT).untilAsserted(() -> assertThat(events(stream)).isEqualTo(2));
    assertThat(body(stream)).contains("\"done\":1");
  }

  @Test
  void finalStatesCloseTheStreamButReviewPendingKeepsItOpen() throws Exception {
    UUID jobId = runningJob();
    MvcResult stream = open(jobId);

    changeAndNotify(
        jobId,
        "update analysis_jobs set status = 'COMPLETED', progress_stage = 'DONE',"
            + " progress_percent = 100, finished_at = now() where id = ?",
        jobId);
    changeAndNotify(
        jobId, "update guides set review_status = 'PENDING' where analysis_job_id = ?", jobId);
    await()
        .atMost(WAIT)
        .untilAsserted(() -> assertThat(body(stream)).contains("\"reviewStatus\":\"PENDING\""));
    assertThat(hub.openConnections()).as("검수 대기는 열어 둔다").isEqualTo(1);

    changeAndNotify(
        jobId, "update guides set review_status = 'APPROVED' where analysis_job_id = ?", jobId);

    await()
        .atMost(WAIT)
        .untilAsserted(
            () -> {
              assertThat(body(stream)).contains("\"reviewStatus\":\"APPROVED\"");
              assertThat(hub.openConnections()).isZero();
            });
  }

  @Test
  void failedJobIsSentOnceAndClosedRightAway() throws Exception {
    UUID jobId = runningJob();
    jdbc.update(
        "update analysis_jobs set status = 'FAILED', failure_code = 'ANALYSIS_TIMEOUT' where id = ?",
        jobId);

    MvcResult stream = open(jobId);

    assertThat(body(stream)).contains("\"status\":\"FAILED\"");
    await().atMost(WAIT).untilAsserted(() -> assertThat(hub.openConnections()).isZero());
  }

  @Test
  void missedAnnouncementsAreCaughtByTheReconcile() throws Exception {
    UUID jobId = runningJob();
    MvcResult stream = open(jobId);

    // 알림 없이 바뀜(알림을 놓친 경우)
    jdbc.update(
        "update analysis_jobs set ai_progress = ?::jsonb where id = ?", progress(42), jobId);
    hub.reconcile();

    assertThat(body(stream)).contains("\"done\":42");
  }

  @Test
  void reconnectedListenerResendsTheCurrentState() throws Exception {
    UUID jobId = runningJob();
    MvcResult stream = open(jobId);
    await().atMost(WAIT).until(() -> listener.backendPid() != null);
    int connects = listener.connectCount();

    // LISTEN 이 끊긴 사이 알림 없이 바뀜
    jdbc.update(
        "update analysis_jobs set ai_progress = ?::jsonb where id = ?", progress(55), jobId);
    jdbc.queryForObject("select pg_terminate_backend(?)", Boolean.class, listener.backendPid());

    await()
        .atMost(Duration.ofSeconds(20))
        .untilAsserted(
            () -> {
              assertThat(listener.connectCount()).isGreaterThan(connects);
              assertThat(body(stream)).contains("\"done\":55");
            });
  }

  @Test
  void overlappingRefreshesNeverSendAnOlderState() throws Exception {
    UUID jobId = runningJob();
    MvcResult stream = open(jobId);
    ExecutorService pool = Executors.newFixedThreadPool(4);
    try {
      for (int done = 1; done <= 40; done++) {
        changeAndNotify(
            jobId,
            "update analysis_jobs set ai_progress = ?::jsonb where id = ?",
            progress(done),
            jobId);
        // 알림 경로와 동시에 갱신·맞추기·재전송이 겹친다
        pool.submit(() -> hub.refresh(jobId));
        pool.submit(hub::reconcile);
        pool.submit(hub::refreshAll);
      }
      pool.shutdown();
      assertThat(pool.awaitTermination(30, TimeUnit.SECONDS)).isTrue();
    } finally {
      pool.shutdownNow();
    }
    await().atMost(WAIT).untilAsserted(() -> assertThat(body(stream)).contains("\"done\":40"));

    List<Integer> sent = new ArrayList<>();
    Matcher matcher = DONE.matcher(body(stream));
    while (matcher.find()) {
      sent.add(Integer.parseInt(matcher.group(1)));
    }
    assertThat(sent).isSorted().doesNotHaveDuplicates();
  }

  @Test
  void shutdownClosesOpenStreamsBeforeTheServerWaitsForThem() throws Exception {
    UUID jobId = runningJob();
    open(jobId);
    assertThat(hub.openConnections()).isEqualTo(1);
    assertThat(hub.getPhase()).isEqualTo(Integer.MAX_VALUE);

    hub.stop();

    await().atMost(WAIT).untilAsserted(() -> assertThat(hub.openConnections()).isZero());
  }

  @Test
  void anotherMembersJobIsNotFound() throws Exception {
    UUID jobId = runningJob();

    mockMvc
        .perform(get(PATH + jobId + "/events").with(as(other)).accept(MediaType.TEXT_EVENT_STREAM))
        .andExpect(status().isNotFound());
    assertThat(hub.openConnections()).isZero();
  }

  @Test
  void loginIsRequired() throws Exception {
    UUID jobId = runningJob();

    mockMvc
        .perform(get(PATH + jobId + "/events").accept(MediaType.TEXT_EVENT_STREAM))
        .andExpect(status().isUnauthorized());
  }
}
