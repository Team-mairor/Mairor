package com.mairor.backend.common.security;

import static com.mairor.backend.testsupport.AuthFlowClient.CHROME_WINDOWS;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SweepProbeHook;
import com.mairor.backend.testsupport.SweepProbeHookConfig;
import java.time.Duration;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 정리 작업이 실제로 예약되어 주기적으로 도는지 확인한다. 테스트 기본 설정은 자동 예약을 꺼 두므로 여기서만 켜고 간격을 짧게 한다. 이 컨텍스트에서는 만료된 세션을 테스트가
 * 직접 지우지 않아도 스스로 지워진다.
 */
@Import({TestcontainersConfiguration.class, SweepProbeHookConfig.class})
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"app.session.sweep.enabled=true", "app.session.sweep.interval=300ms"})
class ExpiredSessionSweepSchedulingTest {

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private SweepProbeHook hook;
  @Autowired private ApplicationContext context;

  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    hook.reset();
  }

  private static boolean waitUntil(Duration timeout, BooleanSupplier condition)
      throws InterruptedException {
    long deadline = System.nanoTime() + timeout.toNanos();
    while (System.nanoTime() < deadline) {
      if (condition.getAsBoolean()) {
        return true;
      }
      Thread.sleep(100);
    }
    return condition.getAsBoolean();
  }

  private boolean rowExists(String sessionId) {
    Integer rows =
        jdbc.queryForObject(
            "select count(*) from spring_session where session_id = ?", Integer.class, sessionId);
    return rows != null && rows > 0;
  }

  @Test
  void theSchedulerIsCreatedWhenEnabled() {
    assertThat(context.getBeansOfType(ExpiredSessionSweepScheduler.class)).hasSize(1);
  }

  @Test
  void anExpiredSessionIsCleanedUpOnItsOwnWithTheHookCalled() throws Exception {
    Login login = flow.login(flow.signUp(), CHROME_WINDOWS);
    String id = AuthFlowClient.sessionId(login.cookie());
    long past = System.currentTimeMillis() - 60_000;
    jdbc.update(
        "update spring_session set last_access_time = ?, expiry_time = ? where session_id = ?",
        past - 259_200_000L,
        past,
        id);

    boolean removed = waitUntil(Duration.ofSeconds(15), () -> !rowExists(id));

    assertThat(removed).as("정리 작업이 만료된 세션을 스스로 지워야 한다").isTrue();
    assertThat(hook.calls)
        .extracting(p -> p.end().sessionId(), p -> p.end().reason())
        .contains(org.assertj.core.groups.Tuple.tuple(id, SessionEndReason.IDLE_EXPIRED));
  }

  @Test
  void anActiveSessionSurvivesTheScheduledSweeps() throws Exception {
    Login login = flow.login(flow.signUp(), CHROME_WINDOWS);
    String id = AuthFlowClient.sessionId(login.cookie());

    Thread.sleep(1_500);

    assertThat(rowExists(id)).isTrue();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }
}
