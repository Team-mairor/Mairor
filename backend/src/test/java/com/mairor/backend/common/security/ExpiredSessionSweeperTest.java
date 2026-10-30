package com.mairor.backend.common.security;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.MutableClock;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import com.mairor.backend.testsupport.SweepProbeHook;
import com.mairor.backend.testsupport.SweepProbeHookConfig;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.test.util.ReflectionTestUtils;

/**
 * 만료된 세션을 지우기 전에 종료 훅을 호출하는 정리 작업을 실제 PostgreSQL 로 확인한다. 정리 작업은 테스트가 직접 실행한다(자동 예약은 테스트 기본 설정에서 꺼져
 * 있다). 만료는 {@code spring_session} 의 시각 컬럼을 과거로 바꿔서 만든다.
 */
@Import({
  TestcontainersConfiguration.class,
  AuthenticatedSessionTestConfig.class,
  SweepProbeHookConfig.class
})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ExpiredSessionSweeperTest {

  private static final Duration RETRY_DELAY = Duration.ofMinutes(5);

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;
  @Autowired private SessionEndNotifier notifier;
  @Autowired private SessionMetrics metrics;
  @Autowired private MeterRegistry registry;
  @Autowired private SweepProbeHook hook;
  @Autowired private ExpiredSessionSweeper realClockSweeper;
  @Autowired private MutableClock appClock;

  private final MutableClock sweepClock = new MutableClock(Instant.now());
  private SessionTestClient raw;
  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    raw = new SessionTestClient(port);
    flow = new AuthFlowClient(raw);
    jdbc.update("delete from spring_session");
    appClock.set(Instant.now());
    sweepClock.set(Instant.now());
    hook.reset();
  }

  private ExpiredSessionSweeper sweeper(int batchSize) {
    return new ExpiredSessionSweeper(
        jdbc,
        sessions,
        notifier,
        metrics,
        new SessionSweepProperties(false, Duration.ofMinutes(1), batchSize, RETRY_DELAY),
        "SPRING_SESSION",
        sweepClock);
  }

  private static String idOf(Login login) {
    return AuthFlowClient.sessionId(login.cookie());
  }

  /** 세션을 만료시킨다. {@code order} 가 작을수록 먼저 만료된 것이다. */
  private void expire(String sessionId, int order) {
    long at = sweepClock.millis() - 600_000 + order * 1_000L;
    jdbc.update(
        "update spring_session set last_access_time = ?, expiry_time = ? where session_id = ?",
        at - 259_200_000L,
        at,
        sessionId);
  }

  private boolean rowExists(String sessionId) {
    Integer rows =
        jdbc.queryForObject(
            "select count(*) from spring_session where session_id = ?", Integer.class, sessionId);
    return rows != null && rows > 0;
  }

  private int attributeRows() {
    Integer rows =
        jdbc.queryForObject("select count(*) from spring_session_attributes", Integer.class);
    return rows == null ? 0 : rows;
  }

  private double counter(String name) {
    var counter = registry.find(name).counter();
    return counter == null ? 0 : counter.count();
  }

  private Login expiredLogin(int order) throws Exception {
    Login login = flow.login(flow.signUp(), CHROME_WINDOWS);
    expire(idOf(login), order);
    return login;
  }

  // ---- 정상 정리 ----

  @Test
  void anExpiredSessionGetsTheHookThenIsDeleted() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, CHROME_WINDOWS);
    expire(idOf(login), 0);
    hook.reset();
    double removedBefore = counter("mairor.session.sweep.removed");

    int removed = sweeper(100).sweep();

    assertThat(removed).isEqualTo(1);
    assertThat(hook.calls).hasSize(1);
    SweepProbeHook.Probe probe = hook.calls.get(0);
    assertThat(probe.end().reason()).isEqualTo(SessionEndReason.IDLE_EXPIRED);
    assertThat(probe.end().sessionId()).isEqualTo(idOf(login));
    assertThat(probe.end().userId()).isEqualTo(account.userId().toString());
    assertThat(probe.rowExisted()).as("지우기 전에 호출").isTrue();
    assertThat(rowExists(idOf(login))).isFalse();
    assertThat(attributeRows()).as("세션 속성 행도 함께 지워진다").isZero();
    assertThat(counter("mairor.session.sweep.removed")).isEqualTo(removedBefore + 1);
  }

  @Test
  void anActiveSessionIsLeftAloneAndStillWorks() throws Exception {
    Login active = flow.login(flow.signUp(), CHROME_WINDOWS);
    hook.reset();

    int removed = sweeper(100).sweep();

    assertThat(removed).isZero();
    assertThat(hook.calls).isEmpty();
    assertThat(rowExists(idOf(active))).isTrue();
    assertThat(flow.me(active.cookie()).status()).isEqualTo(200);
  }

  @Test
  void onlyTheExpiredUsersSessionIsRemoved() throws Exception {
    Account expiredUser = flow.signUp();
    Account activeUser = flow.signUp();
    Login expired = flow.login(expiredUser, CHROME_WINDOWS);
    Login active = flow.login(activeUser, CHROME_WINDOWS);
    expire(idOf(expired), 0);
    hook.reset();

    sweeper(100).sweep();

    assertThat(hook.calls)
        .extracting(p -> p.end().userId())
        .containsExactly(expiredUser.userId().toString());
    assertThat(flow.me(active.cookie()).status()).isEqualTo(200);
  }

  @Test
  void anExpiredAnonymousSessionIsDeletedWithoutCallingTheHook() throws Exception {
    Response anonymous = raw.get("/test-support/anonymous-session", null);
    String anonymousId = AuthFlowClient.sessionId(anonymous.sessionCookieValue());
    expire(anonymousId, 0);
    hook.reset();

    int removed = sweeper(100).sweep();

    assertThat(removed).isEqualTo(1);
    assertThat(hook.calls).isEmpty();
    assertThat(rowExists(anonymousId)).isFalse();
  }

  // ---- 훅 실패 ----

  @Test
  void whenTheHookFailsTheRowStaysAndIsRetriedAfterTheRetryDelay() throws Exception {
    Login login = expiredLogin(0);
    String id = idOf(login);
    hook.reset();
    hook.failingSessionIds.add(id);
    double failedBefore = counter("mairor.session.sweep.failed");

    int first = sweeper(100).sweep();

    assertThat(first).isZero();
    assertThat(rowExists(id)).as("훅이 실패하면 행을 남긴다").isTrue();
    assertThat(counter("mairor.session.sweep.failed")).isEqualTo(failedBefore + 1);
    assertThat(hook.calls).hasSize(1);
  }

  @Test
  void aFailedRowIsSkippedUntilTheRetryDelayPassesThenRetried() throws Exception {
    String id = idOf(expiredLogin(0));
    hook.reset();
    hook.failingSessionIds.add(id);
    ExpiredSessionSweeper sweeper = sweeper(100);
    sweeper.sweep();

    // 재시도 간격 안에서는 다시 시도하지 않는다
    sweepClock.advance(RETRY_DELAY.minusSeconds(30));
    sweeper.sweep();
    assertThat(hook.calls).hasSize(1);

    // 간격이 지나고 훅이 고쳐지면 정리된다
    sweepClock.advance(Duration.ofMinutes(1));
    hook.failingSessionIds.clear();
    int removed = sweeper.sweep();

    assertThat(removed).isEqualTo(1);
    assertThat(hook.calls).hasSize(2);
    assertThat(rowExists(id)).isFalse();
  }

  @Test
  void aFailedRowIsRetriedAfterTheDelayEvenIfStillFailing() throws Exception {
    String id = idOf(expiredLogin(0));
    hook.reset();
    hook.failingSessionIds.add(id);
    ExpiredSessionSweeper sweeper = sweeper(100);
    sweeper.sweep();

    sweepClock.advance(RETRY_DELAY.plusSeconds(1));
    sweeper.sweep();

    assertThat(hook.calls).hasSize(2);
    assertThat(rowExists(id)).isTrue();
  }

  // ---- 상한과 굶김 방지 ----

  @Test
  void aSweepTriesNoMoreThanTheBatchSizeAndTheRestContinuesNextTime() throws Exception {
    for (int i = 0; i < 5; i++) {
      expiredLogin(i);
    }
    ExpiredSessionSweeper sweeper = sweeper(2);

    assertThat(sweeper.sweep()).isEqualTo(2);
    assertThat(sweeper.sweep()).isEqualTo(2);
    assertThat(sweeper.sweep()).isEqualTo(1);
    assertThat(sweeper.sweep()).isZero();
    assertThat(jdbc.queryForObject("select count(*) from spring_session", Integer.class)).isZero();
  }

  /** 계속 실패하는 세션이 앞을 막고 있어도 뒤의 정상 세션이 정리된다. */
  @Test
  void rowsThatKeepFailingDoNotStarveTheHealthyOnesBehindThem() throws Exception {
    List<String> poison =
        List.of(idOf(expiredLogin(0)), idOf(expiredLogin(1)), idOf(expiredLogin(2)));
    String healthy1 = idOf(expiredLogin(3));
    String healthy2 = idOf(expiredLogin(4));
    hook.reset();
    hook.failingSessionIds.addAll(poison);
    ExpiredSessionSweeper sweeper = sweeper(2);

    // 1회: 앞의 두 개가 시도 상한을 쓰고 실패
    assertThat(sweeper.sweep()).isZero();
    // 2회: 실패한 두 개는 건너뛰고, 세 번째(실패)와 정상 하나를 시도
    assertThat(sweeper.sweep()).isEqualTo(1);
    // 3회: 실패한 세 개를 건너뛰고 남은 정상 하나를 정리
    assertThat(sweeper.sweep()).isEqualTo(1);

    assertThat(rowExists(healthy1)).isFalse();
    assertThat(rowExists(healthy2)).isFalse();
    assertThat(poison).allMatch(this::rowExists);
  }

  // ---- 시각 기준 ----

  /** 정리 기준은 Spring Session 이 쓰는 실제 시각이다. 서비스의 시계(테스트가 옮기는 시계)를 따라가면 멀쩡한 세션이 지워진다. */
  @Test
  void theDefaultSweeperIgnoresTheApplicationClock() throws Exception {
    Login active = flow.login(flow.signUp(), CHROME_WINDOWS);
    hook.reset();
    appClock.set(Instant.now().plus(Duration.ofDays(60)));

    int removed = realClockSweeper.sweep();

    assertThat(removed).isZero();
    assertThat(rowExists(idOf(active))).isTrue();
    assertThat(hook.calls).isEmpty();
  }

  // ---- 설정 ----

  @Test
  void springsOwnCleanupIsSwitchedOff() {
    Object repository = sessions;
    assertThat(ReflectionTestUtils.getField(repository, "cleanupCron")).isEqualTo("-");
    assertThat(ReflectionTestUtils.getField(repository, "taskScheduler")).isNull();
  }

  @Test
  void aTableNameThatIsNotAPlainIdentifierIsRejected() {
    assertThatThrownBy(
            () ->
                new ExpiredSessionSweeper(
                    jdbc,
                    sessions,
                    notifier,
                    metrics,
                    new SessionSweepProperties(false, Duration.ofMinutes(1), 10, RETRY_DELAY),
                    "spring_session; drop table users",
                    sweepClock))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
