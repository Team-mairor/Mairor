package com.mairor.backend.analysis.sse;

import com.mairor.backend.analysis.notify.AnalysisJobNotifier;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import javax.sql.DataSource;
import org.postgresql.PGConnection;
import org.postgresql.PGNotification;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * 분석 작업 변경 알림({@link AnalysisJobNotifier#CHANNEL})을 받아 {@link SseHub}에 그 작업을 다시 보내라고 한다. api 프로세스마다
 * 하나 뜬다.
 *
 * <p>연결 풀(Hikari) 밖에 DB 연결 하나를 따로 열어 {@code LISTEN} 한다. 풀의 연결은 돌려줄 때 다른 요청이 쓰므로 LISTEN 을 쥐고 있을 수
 * 없다. 끊기면 1초부터 두 배씩(최대 {@code listenRetryMax}) 기다렸다 다시 붙고, 다시 붙으면 그 사이 알림을 놓쳤을 수 있어 열린 작업 전부를 다시
 * 보낸다.
 */
@Component
@Profile("!worker")
public class PgNotificationListener implements SmartLifecycle {

  private static final Logger log = LoggerFactory.getLogger(PgNotificationListener.class);
  private static final long FIRST_RETRY_MILLIS = 1000;

  private final DataSource dataSource;
  private final SseHub hub;
  private final SseProperties properties;
  private final AtomicInteger connects = new AtomicInteger();
  private volatile boolean running;
  private volatile Connection connection;
  private volatile Integer backendPid;
  private Thread thread;

  PgNotificationListener(DataSource dataSource, SseHub hub, SseProperties properties) {
    this.dataSource = dataSource;
    this.hub = hub;
    this.properties = properties;
  }

  @Override
  public void start() {
    running = true;
    thread = Thread.ofPlatform().daemon().name("analysis-job-listener").start(this::loop);
  }

  private void loop() {
    long retryMillis = FIRST_RETRY_MILLIS;
    boolean first = true;
    while (running) {
      try (Connection listening = open()) {
        listen(listening);
        connection = listening;
        connects.incrementAndGet();
        if (!first) {
          log.info("분석 상태 LISTEN 다시 연결, 열린 SSE 에 지금 상태를 다시 보냄");
          hub.refreshAll();
        }
        first = false;
        retryMillis = FIRST_RETRY_MILLIS;
        receive(listening);
      } catch (SQLException | RuntimeException e) {
        if (!running) {
          break;
        }
        first = false;
        log.warn("분석 상태 LISTEN 연결 끊김. {}ms 뒤 다시 붙음: {}", retryMillis, e.getMessage());
        sleep(retryMillis);
        retryMillis = Math.min(retryMillis * 2, properties.listenRetryMax().toMillis());
      } finally {
        connection = null;
        backendPid = null;
      }
    }
  }

  private void listen(Connection listening) throws SQLException {
    listening.setAutoCommit(true);
    try (Statement statement = listening.createStatement()) {
      statement.execute("LISTEN " + AnalysisJobNotifier.CHANNEL);
      try (ResultSet rs = statement.executeQuery("select pg_backend_pid()")) {
        rs.next();
        backendPid = rs.getInt(1);
      }
    }
  }

  private void receive(Connection listening) throws SQLException {
    PGConnection pg = listening.unwrap(PGConnection.class);
    int timeout = (int) properties.listenPollTimeout().toMillis();
    while (running) {
      // 연결이 끊겼으면 여기서 SQLException 이 난다
      PGNotification[] notifications = pg.getNotifications(timeout);
      if (notifications == null) {
        continue;
      }
      for (PGNotification notification : notifications) {
        dispatch(notification.getParameter());
      }
    }
  }

  private void dispatch(String payload) {
    UUID jobId;
    try {
      jobId = UUID.fromString(payload);
    } catch (IllegalArgumentException e) {
      log.warn("분석 상태 알림의 작업 ID 를 읽지 못함 payload={}", payload);
      return;
    }
    hub.refresh(jobId);
  }

  /** 풀 밖의 연결. 풀이 Hikari 면 같은 주소·계정으로 직접 연다. */
  private Connection open() throws SQLException {
    if (dataSource.isWrapperFor(HikariDataSource.class)) {
      HikariDataSource hikari = dataSource.unwrap(HikariDataSource.class);
      return DriverManager.getConnection(
          hikari.getJdbcUrl(), hikari.getUsername(), hikari.getPassword());
    }
    throw new SQLException("Hikari 가 아닌 DataSource 라 LISTEN 연결을 따로 열 수 없습니다: " + dataSource);
  }

  private void sleep(long millis) {
    try {
      Thread.sleep(millis);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      running = false;
    }
  }

  /** 지금 LISTEN 중인 DB 세션의 pid. 붙어 있지 않으면 {@code null}. 테스트가 연결을 끊어 볼 때 쓴다. */
  public Integer backendPid() {
    return backendPid;
  }

  /** 지금까지 LISTEN 에 붙은 횟수. */
  public int connectCount() {
    return connects.get();
  }

  @Override
  public void stop() {
    running = false;
    Connection current = connection;
    if (current != null) {
      try {
        current.close();
      } catch (SQLException e) {
        log.debug("LISTEN 연결 닫기 실패", e);
      }
    }
    if (thread != null) {
      try {
        thread.join(properties.listenPollTimeout().toMillis() + 1000);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
      }
    }
  }

  @Override
  public boolean isRunning() {
    return running;
  }

  /** {@link SseHub}가 연결을 닫은 뒤에 멈춘다. */
  @Override
  public int getPhase() {
    return SmartLifecycle.DEFAULT_PHASE - 1;
  }
}
