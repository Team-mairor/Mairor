package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthenticatedSessionTestConfig;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 실제 HTTP + PostgreSQL 에서 컨트롤러가 저장한 인증이 JDBC 세션을 거쳐 다음 요청에 유지되는지, 그리고 Spring Session 의 {@code
 * PRINCIPAL_NAME} 색인이 userId 로 채워지는지 확인한다. MockMvc 는 세션 직렬화·재조회와 실제 쿠키를 거치지 않아 이 검증에 쓸 수 없다.
 */
@Import({TestcontainersConfiguration.class, AuthenticatedSessionTestConfig.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AuthenticatedSessionTest {

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;

  private SessionTestClient client;

  @BeforeEach
  void setUp() {
    client = new SessionTestClient(port);
    jdbc.update("delete from spring_session");
  }

  private Response login(UUID userId) throws Exception {
    return client.post("/test-support/login?userId=" + userId, null);
  }

  @Test
  void authenticationSurvivesTheNextRequestThroughTheJdbcSession() throws Exception {
    UUID userId = UUID.randomUUID();
    Response login = login(userId);
    String cookie = login.sessionCookieValue();
    assertThat(login.status()).isEqualTo(200);
    assertThat(cookie).as("로그인 응답에 세션 쿠키가 있어야 한다").isNotBlank();

    Response whoami = client.get("/test-support/whoami", cookie);

    assertThat(whoami.status()).isEqualTo(200);
    assertThat(whoami.body()).isEqualTo(userId.toString());
  }

  @Test
  void aRequestWithoutTheCookieIsNotAuthenticated() throws Exception {
    Response whoami = client.get("/test-support/whoami", null);

    assertThat(whoami.status()).isEqualTo(401);
  }

  @Test
  void aTamperedCookieIsNotAuthenticated() throws Exception {
    Response login = login(UUID.randomUUID());
    String tampered = "x" + login.sessionCookieValue();

    assertThat(client.get("/test-support/whoami", tampered).status()).isEqualTo(401);
  }

  @Test
  void principalNameIsTheUserIdInTheSessionTable() throws Exception {
    UUID userId = UUID.randomUUID();
    login(userId);

    List<String> principals =
        jdbc.queryForList(
            "select principal_name from spring_session where principal_name is not null",
            String.class);

    assertThat(principals).containsExactly(userId.toString());
  }

  @Test
  void sessionsOfAUserAreFoundByPrincipalName() throws Exception {
    UUID userId = UUID.randomUUID();
    UUID otherUserId = UUID.randomUUID();
    login(userId);
    login(userId);
    login(otherUserId);

    assertThat(sessions.findByPrincipalName(userId.toString())).hasSize(2);
    assertThat(sessions.findByPrincipalName(otherUserId.toString())).hasSize(1);
    assertThat(sessions.findByPrincipalName(UUID.randomUUID().toString())).isEmpty();
  }
}
