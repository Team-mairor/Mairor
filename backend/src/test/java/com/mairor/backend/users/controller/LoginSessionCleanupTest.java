package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SessionTestClient.Response;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.DeferredCsrfToken;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.session.FindByIndexNameSessionRepository;

/**
 * 로그인 세션을 만드는 도중 실패하면 인증된 세션이 남지 않는지 실제 HTTP + PostgreSQL 로 확인한다. 세션 발급은 인증 컨텍스트를 먼저 저장하고 그 뒤에 로그인
 * 시각·기기·CSRF 토큰을 붙이므로, 뒤 단계가 실패해도 앞 단계의 인증 상태가 응답을 커밋할 때 저장되면 "로그인은 실패했는데 내 계정 조회는 인증됨"이 된다.
 *
 * <p>CSRF 토큰 발급(세션 발급의 마지막 단계)을 실패시키는 저장소를 운영 저장소 대신 끼워 넣는다. 로그인 외의 요청은 영향을 받지 않는다.
 */
@Import({TestcontainersConfiguration.class, LoginSessionCleanupTest.FailingCsrf.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class LoginSessionCleanupTest {

  /** 켜 두면 로그인이 호출하는 토큰 교체({@code saveToken(null, …)})가 실패한다. 그 밖에는 운영과 같은 저장소에 맡긴다. */
  static class FailableCsrfTokenRepository implements CsrfTokenRepository {

    private final CsrfTokenRepository delegate = new HttpSessionCsrfTokenRepository();
    volatile boolean failIssue;

    @Override
    public CsrfToken generateToken(HttpServletRequest request) {
      return delegate.generateToken(request);
    }

    @Override
    public void saveToken(
        CsrfToken token, HttpServletRequest request, HttpServletResponse response) {
      if (token == null && failIssue) {
        throw new IllegalStateException("CSRF 토큰 발급 실패(테스트가 주입)");
      }
      delegate.saveToken(token, request, response);
    }

    @Override
    public CsrfToken loadToken(HttpServletRequest request) {
      return delegate.loadToken(request);
    }

    @Override
    public DeferredCsrfToken loadDeferredToken(
        HttpServletRequest request, HttpServletResponse response) {
      return delegate.loadDeferredToken(request, response);
    }
  }

  @TestConfiguration(proxyBeanMethods = false)
  static class FailingCsrf {

    @Bean
    @Primary
    FailableCsrfTokenRepository failableCsrfTokenRepository() {
      return new FailableCsrfTokenRepository();
    }
  }

  @LocalServerPort private int port;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private FailableCsrfTokenRepository csrfRepository;
  @Autowired private FindByIndexNameSessionRepository<?> sessions;

  private AuthFlowClient flow;

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    jdbc.update("delete from spring_session");
  }

  @AfterEach
  void tearDown() {
    csrfRepository.failIssue = false;
  }

  @Test
  void aLoginThatFailsWhileBuildingTheSessionLeavesNoAuthenticatedSession() throws Exception {
    Account account = flow.signUp();
    csrfRepository.failIssue = true;

    Response failed =
        flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);

    assertThat(failed.status()).isEqualTo(500);
    assertThat(failed.body()).contains("INTERNAL_ERROR");
    assertThat(sessions.findByPrincipalName(account.userId().toString())).isEmpty();
    if (failed.sessionCookieValue() != null) {
      assertThat(flow.me(failed.sessionCookieValue()).status()).isEqualTo(401);
    }
  }

  @Test
  void aLoginThatFailedHalfwayDoesNotLogOutOrBreakTheNextAttempt() throws Exception {
    Account account = flow.signUp();
    csrfRepository.failIssue = true;
    flow.loginRaw(account.email(), AuthFlowClient.PASSWORD, AuthFlowClient.CHROME_WINDOWS);
    csrfRepository.failIssue = false;

    AuthFlowClient.Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);

    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    assertThat(sessions.findByPrincipalName(account.userId().toString())).hasSize(1);
  }

  @Test
  void aFailedAccountSwitchDoesNotLogTheSecondAccountIn() throws Exception {
    Account first = flow.signUp();
    Account second = flow.signUp();
    AuthFlowClient.Login firstLogin = flow.login(first, AuthFlowClient.CHROME_WINDOWS);
    csrfRepository.failIssue = true;

    Response failed =
        flow.loginRaw(
            second.email(),
            AuthFlowClient.PASSWORD,
            AuthFlowClient.CHROME_WINDOWS,
            firstLogin.cookie());
    csrfRepository.failIssue = false;

    assertThat(failed.status()).isEqualTo(500);
    // 두 번째 계정으로는 어떤 세션도 남지 않는다(첫 번째 계정의 세션은 전환을 시작하면서 이미 폐기됐다)
    assertThat(sessions.findByPrincipalName(second.userId().toString())).isEmpty();
    if (failed.sessionCookieValue() != null) {
      assertThat(flow.me(failed.sessionCookieValue()).status()).isEqualTo(401);
    }
  }
}
