package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import io.micrometer.core.instrument.MeterRegistry;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 세션 저장소(DB)가 실패할 때 실제 HTTP 응답이 공통 오류 형식으로 나가는지 확인한다. 장애의 종류를 구분해서 만든다.
 *
 * <ul>
 *   <li><b>일시적 장애</b>(연결 풀이 바닥남, 연결 실패 SQLSTATE 08006): {@code 503 SERVICE_UNAVAILABLE}. 인증
 *       실패(401)가 아니다.
 *   <li><b>서버 문제</b>(스키마 불일치, 일반 DB 오류): {@code 500 INTERNAL_ERROR}. 503 이 아니다.
 *   <li><b>손상된 세션</b>(저장된 값을 읽지 못함): {@code 401} 과 쿠키 만료.
 *   <li><b>저장할 수 없는 값</b>(직렬화 실패, 서버 버그): {@code 500}. "로그인 만료"(401)로 보이면 안 된다.
 * </ul>
 *
 * 어느 쪽이든 세션을 저장하지 못했는데 로그인 성공이 나가거나, 지우지 못했는데 로그아웃 성공(204)이 나가지 않아야 한다. 연결 풀은 3개로 줄이고 대기 시간을 짧게 해서
 * 풀 소진을 빠르게 만든다.
 */
@Import({TestcontainersConfiguration.class, AuthenticatedSessionTestConfig.class})
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
      "spring.datasource.hikari.maximum-pool-size=3",
      "spring.datasource.hikari.connection-timeout=300"
    })
class SessionStoreFailureTest {

  private static final String TRIGGER = "mairor_session_failure";
  private static final int POOL_SIZE = 3;

  /** 연결이 끊긴 것처럼 보이는 DB 오류(SQLSTATE 08006). 연결 풀이 그 연결을 버려서 이어지는 롤백도 실패한다. */
  private static final String CONNECTION_FAILURE = "08006";

  /** 다시 시도하면 되는 일시적 DB 오류(SQLSTATE 40001, 직렬화 실패). 롤백은 정상적으로 된다. */
  private static final String TRANSIENT_FAILURE = "40001";

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private DataSource dataSource;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;
  @Autowired private MeterRegistry registry;

  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    jdbc.update("delete from spring_session");
  }

  @AfterEach
  void restore() {
    jdbc.execute("drop trigger if exists " + TRIGGER + " on spring_session");
    jdbc.execute("drop function if exists " + TRIGGER + "()");
    for (String table : new String[] {"spring_session", "spring_session_attributes"}) {
      Boolean renamed =
          jdbc.queryForObject("select to_regclass('" + table + "_x') is not null", Boolean.class);
      if (Boolean.TRUE.equals(renamed)) {
        jdbc.execute("alter table " + table + "_x rename to " + table);
      }
    }
  }

  // ---- 장애 만들기 ----

  /**
   * 연결 풀을 모두 쥔다. 서버는 연결을 기다리다 시간 초과로 연결 실패(일시 장애)를 받는다. 풀을 쥐고 있는 동안에는 테스트도 {@code jdbc} 를 쓰지 못한다.
   */
  private List<Connection> exhaustPool() throws SQLException {
    List<Connection> held = new ArrayList<>();
    for (int i = 0; i < POOL_SIZE; i++) {
      held.add(dataSource.getConnection());
    }
    return held;
  }

  private static void release(List<Connection> held) throws SQLException {
    for (Connection connection : held) {
      connection.close();
    }
  }

  /** 세션 테이블에 접근하면 "테이블 없음" 오류가 난다. 스키마가 맞지 않는 서버 문제를 흉내 낸다. */
  private void breakSchema() {
    jdbc.execute("alter table spring_session rename to spring_session_x");
    jdbc.execute("alter table spring_session_attributes rename to spring_session_attributes_x");
  }

  private void fixSchema() {
    jdbc.execute("alter table spring_session_x rename to spring_session");
    jdbc.execute("alter table spring_session_attributes_x rename to spring_session_attributes");
  }

  /**
   * {@code operation}(INSERT·UPDATE·DELETE) 문이 spring_session 에 실행되면 DB 가 오류를 낸다. {@code sqlState}
   * 가 {@code null} 이면 일반 오류 (서버 문제)이고, {@link #CONNECTION_FAILURE} 면 연결 실패(일시 장애)다.
   */
  private void failOn(String operation, String sqlState) {
    String using = sqlState == null ? "" : " using errcode = '" + sqlState + "'";
    jdbc.execute(
        "create or replace function "
            + TRIGGER
            + "() returns trigger as $$ begin raise exception 'blocked by test'"
            + using
            + "; end $$ language plpgsql");
    jdbc.execute(
        "create trigger "
            + TRIGGER
            + " before "
            + operation
            + " on spring_session for each row execute function "
            + TRIGGER
            + "()");
  }

  private void stopFailing() {
    jdbc.execute("drop trigger if exists " + TRIGGER + " on spring_session");
  }

  // ---- 응답 확인 ----

  private static void assertServiceUnavailable(Response response) {
    assertThat(response.status()).isEqualTo(503);
    assertThat(response.body())
        .contains("\"code\":\"SERVICE_UNAVAILABLE\"")
        .doesNotContain("<html");
  }

  private static void assertServerError(Response response) {
    assertThat(response.status()).isEqualTo(500);
    assertThat(response.body()).contains("\"code\":\"INTERNAL_ERROR\"").doesNotContain("<html");
  }

  private double failures(String cause) {
    var counter = registry.find("mairor.session.failures").tag("cause", cause).counter();
    return counter == null ? 0 : counter.count();
  }

  // ---- 조회 실패 ----

  @Test
  void whenTheStoreIsUnreachableTheAnswerIs503NotAnUnauthenticated401() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    List<Connection> held = exhaustPool();
    Response whileDown;
    try {
      whileDown = flow.me(login.cookie());
    } finally {
      release(held);
    }

    assertServiceUnavailable(whileDown);
    assertThat(whileDown.sessionCookieCount()).isZero();
    // 장애가 끝나면 같은 쿠키로 그대로 이용할 수 있다(세션을 잃지 않았다)
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  @Test
  void aSchemaMismatchIsAServerErrorNotAnOutage() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    breakSchema();
    Response broken;
    try {
      broken = flow.me(login.cookie());
    } finally {
      fixSchema();
    }

    assertServerError(broken);
    assertThat(broken.sessionCookieCount()).isZero();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 저장 실패 ----

  @Test
  void aLoginWhoseSessionCannotBeSavedBecauseTheStoreIsDownDoesNotAnswerSuccess() throws Exception {
    Account account = flow.signUp();
    failOn("insert", CONNECTION_FAILURE);
    Response failed;
    try {
      failed =
          flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);
    } finally {
      stopFailing();
    }

    assertServiceUnavailable(failed);
    assertThat(failed.body()).doesNotContain("csrfToken");
    assertThat(failed.sessionCookieValue()).isNull();
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
    // 장애가 끝나면 다시 로그인된다
    Login again = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    assertThat(flow.me(again.cookie()).status()).isEqualTo(200);
  }

  @Test
  void aLoginWhoseSessionCannotBeSavedBecauseOfAGeneralErrorIsAServerError() throws Exception {
    Account account = flow.signUp();
    failOn("insert", null);
    Response failed;
    try {
      failed =
          flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);
    } finally {
      stopFailing();
    }

    assertServerError(failed);
    assertThat(failed.body()).doesNotContain("csrfToken");
    assertThat(failed.sessionCookieValue()).isNull();
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
  }

  @Test
  void aRequestWhoseSessionUpdateCannotBeSavedBecauseTheStoreIsDownAnswers503() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failOn("update", TRANSIENT_FAILURE);
    Response failed;
    try {
      failed = flow.me(login.cookie());
    } finally {
      stopFailing();
    }

    assertServiceUnavailable(failed);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 삭제 실패 ----

  /** 컨트롤러 안에서 세션을 지우다 실패한다(MVC 예외 처리). 일시 장애면 503 이다. */
  @Test
  void aLogoutWhoseSessionCannotBeDeletedBecauseTheStoreIsDownIs503() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failOn("delete", CONNECTION_FAILURE);
    Response failed;
    try {
      failed = flow.logout(login.cookie(), login.csrfToken());
    } finally {
      stopFailing();
    }

    assertServiceUnavailable(failed);
    // 로그아웃이 끝나지 않았으므로 세션은 살아 있고, 다시 로그아웃할 수 있다
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    assertThat(flow.logout(login.cookie(), login.csrfToken()).status()).isEqualTo(204);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(401);
  }

  @Test
  void aLogoutWhoseSessionCannotBeDeletedBecauseOfAGeneralErrorIsAServerError() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    failOn("delete", null);
    Response failed;
    try {
      failed = flow.logout(login.cookie(), login.csrfToken());
    } finally {
      stopFailing();
    }

    assertServerError(failed);
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 읽을 수 없는 세션과 저장할 수 없는 값 ----

  @Test
  void aSessionThatCannotBeReadBackIsAnsweredWith401AndItsCookieIsExpired() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    jdbc.update(
        "update spring_session_attributes set attribute_bytes = decode('00', 'hex') "
            + "where attribute_name = 'SPRING_SECURITY_CONTEXT'");

    Response broken = flow.me(login.cookie());

    assertThat(broken.status()).isEqualTo(401);
    assertThat(broken.body()).contains("\"code\":\"UNAUTHORIZED\"");
    // 같은 쿠키로 계속 실패하지 않게 브라우저가 쿠키를 버린다
    assertThat(broken.sessionCookieCount()).isEqualTo(1);
    assertThat(broken.sessionCookieMaxAge()).isZero();
    // 쿠키 없이 다시 로그인하면 된다
    Login again = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    assertThat(flow.me(again.cookie()).status()).isEqualTo(200);
  }

  /**
   * 저장된 세션을 읽지 못하는 것(역직렬화)과 새 속성을 저장하지 못하는 것(직렬화)은 같은 예외 종류로 나오지만 뜻이 다르다. 앞은 사용자의 세션이 못 쓰게 된 것이라 다시
   * 로그인하게 하고, 뒤는 서버 버그라서 "로그인 만료"로 보이면 안 된다.
   */
  @Test
  void aSessionAttributeThatCannotBeSerializedIsAServerErrorNotAnExpiredLogin() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);

    Response failed = flow.get("/test-support/unserializable", login.cookie());

    assertServerError(failed);
    // 쿠키를 만료시키지 않고, 기존 세션은 그대로 쓸 수 있다
    assertThat(failed.sessionCookieCount()).isZero();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
  }

  // ---- 지표 ----

  @Test
  void failuresAreCountedByTheirCause() throws Exception {
    Account account = flow.signUp();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    double storeBefore = failures("store_unavailable");
    double unexpectedBefore = failures("unexpected");
    double corruptedBefore = failures("corrupted_session");

    List<Connection> held = exhaustPool();
    try {
      flow.me(login.cookie());
    } finally {
      release(held);
    }
    flow.get("/test-support/unserializable", login.cookie());
    jdbc.update(
        "update spring_session_attributes set attribute_bytes = decode('00', 'hex') "
            + "where attribute_name = 'SPRING_SECURITY_CONTEXT'");
    flow.me(login.cookie());

    assertThat(failures("store_unavailable")).isEqualTo(storeBefore + 1);
    assertThat(failures("unexpected")).isEqualTo(unexpectedBefore + 1);
    assertThat(failures("corrupted_session")).isEqualTo(corruptedBefore + 1);
  }

  // ---- 장애 중에도 세션과 무관한 요청은 정상 ----

  @Test
  void requestsThatDoNotTouchTheSessionStoreAreUnaffected() throws Exception {
    breakSchema();
    try {
      assertThat(flow.get("/health", null).status()).isEqualTo(200);
    } finally {
      fixSchema();
    }
  }
}
