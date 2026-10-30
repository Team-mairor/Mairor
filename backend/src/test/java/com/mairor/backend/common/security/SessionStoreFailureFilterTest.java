package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.spy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import com.mairor.backend.common.error.ErrorResponseWriter;
import com.mairor.backend.common.security.SessionStoreFailureFilter.Cause;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import java.io.IOException;
import java.sql.SQLException;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.core.serializer.support.SerializationFailedException;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.CookieSerializer.CookieValue;
import org.springframework.transaction.CannotCreateTransactionException;
import tools.jackson.databind.json.JsonMapper;

class SessionStoreFailureFilterTest {

  private final CookieSerializer cookies = mock(CookieSerializer.class);
  private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
  private final SessionStoreFailureFilter filter =
      new SessionStoreFailureFilter(
          new ErrorResponseWriter(JsonMapper.builder().build()),
          cookies,
          new SessionMetrics(registry));
  private final MockHttpServletRequest request = new MockHttpServletRequest();
  private MockHttpServletResponse response = new MockHttpServletResponse();

  private void run(FilterChain chain) throws Exception {
    filter.doFilter(request, response, chain);
  }

  /** 체인이 검사 예외를 포함해 무엇이든 던지는 상황을 만든다(필터는 서블릿 시그니처 밖의 예외도 받아야 한다). */
  private static FilterChain throwing(Exception e) {
    return (req, res) -> FilterChainSupport.<RuntimeException>sneakyThrow(e);
  }

  private static final class FilterChainSupport {
    @SuppressWarnings("unchecked")
    static <T extends Throwable> void sneakyThrow(Throwable e) throws T {
      throw (T) e;
    }
  }

  // ---- 분류 ----

  @Test
  void connectionAndTransientFailuresAreStoreFailures() {
    assertThat(SessionStoreFailureFilter.classify(new CannotGetJdbcConnectionException("pool")))
        .isEqualTo(Cause.STORE_UNAVAILABLE);
    assertThat(SessionStoreFailureFilter.classify(new DataAccessResourceFailureException("down")))
        .isEqualTo(Cause.STORE_UNAVAILABLE);
    assertThat(SessionStoreFailureFilter.classify(new CannotAcquireLockException("deadlock")))
        .isEqualTo(Cause.STORE_UNAVAILABLE);
    assertThat(SessionStoreFailureFilter.classify(new QueryTimeoutException("slow")))
        .isEqualTo(Cause.STORE_UNAVAILABLE);
    assertThat(
            SessionStoreFailureFilter.classify(
                new CannotCreateTransactionException("Could not open JPA EntityManager")))
        .isEqualTo(Cause.STORE_UNAVAILABLE);
  }

  @Test
  void aStoreFailureWrappedInOtherExceptionsIsStillAStoreFailure() {
    Throwable wrapped =
        new ServletException(new IllegalStateException(new CannotGetJdbcConnectionException("x")));

    assertThat(SessionStoreFailureFilter.classify(wrapped)).isEqualTo(Cause.STORE_UNAVAILABLE);
  }

  @Test
  void aServerProblemInTheDatabaseIsNotAStoreOutage() {
    assertThat(SessionStoreFailureFilter.classify(new BadSqlGrammarException("t", "select", null)))
        .isEqualTo(Cause.UNEXPECTED);
    assertThat(SessionStoreFailureFilter.classify(new DataIntegrityViolationException("dup")))
        .isEqualTo(Cause.UNEXPECTED);
    assertThat(SessionStoreFailureFilter.classify(new SQLException("raw, unclassified")))
        .isEqualTo(Cause.UNEXPECTED);
  }

  @Test
  void anUnreadableStoredValueIsACorruptedSessionEvenInsideAStoreException() {
    Throwable unreadable = new UnreadableSessionException("bad", new IllegalStateException());
    Throwable wrapped = new DataAccessResourceFailureException("wrapper", unreadable);

    assertThat(SessionStoreFailureFilter.classify(unreadable)).isEqualTo(Cause.CORRUPTED_SESSION);
    assertThat(SessionStoreFailureFilter.classify(wrapped)).isEqualTo(Cause.CORRUPTED_SESSION);
  }

  /** 저장할 때(직렬화)의 실패는 서버 버그다. 읽을 때의 실패({@link UnreadableSessionException})만 손상된 세션이다. */
  @Test
  void aFailureToSerializeANewValueIsNotACorruptedSession() {
    assertThat(
            SessionStoreFailureFilter.classify(
                new SerializationFailedException("Failed to serialize object")))
        .isEqualTo(Cause.UNEXPECTED);
  }

  @Test
  void anythingElseIsUnexpected() {
    assertThat(SessionStoreFailureFilter.classify(new IllegalStateException("bug")))
        .isEqualTo(Cause.UNEXPECTED);
  }

  @Test
  void aSelfReferencingCauseDoesNotLoopForever() {
    IllegalStateException loop =
        new IllegalStateException("loop") {
          @Override
          public synchronized Throwable getCause() {
            return this;
          }
        };

    assertThat(SessionStoreFailureFilter.classify(loop)).isEqualTo(Cause.UNEXPECTED);
  }

  // ---- 응답 ----

  @Test
  void aStoreFailureBecomes503AndDropsWhatWasAlreadyWritten() throws Exception {
    run(
        (req, res) -> {
          res.getWriter().write("{\"user\":\"login succeeded\"}");
          ((MockHttpServletResponse) res).setHeader("Cache-Control", "no-store");
          throw new CannotGetJdbcConnectionException("pool exhausted");
        });

    assertThat(response.getStatus()).isEqualTo(503);
    assertThat(response.getContentAsString())
        .contains("\"code\":\"SERVICE_UNAVAILABLE\"")
        .doesNotContain("login succeeded");
    assertThat(response.getContentType()).startsWith("application/json");
    verifyNoInteractions(cookies);
  }

  @Test
  void aCorruptedSessionBecomes401AndExpiresTheSessionCookie() throws Exception {
    run(throwing(new UnreadableSessionException("cannot read", new IllegalStateException())));

    assertThat(response.getStatus()).isEqualTo(401);
    assertThat(response.getContentAsString()).contains("\"code\":\"UNAUTHORIZED\"");
    ArgumentCaptor<CookieValue> captured = ArgumentCaptor.forClass(CookieValue.class);
    verify(cookies).writeCookieValue(captured.capture());
    assertThat(captured.getValue().getCookieValue()).isEmpty();
  }

  @Test
  void anUnexpectedExceptionBecomes500Json() throws Exception {
    run(throwing(new IllegalStateException("secret internal detail")));

    assertThat(response.getStatus()).isEqualTo(500);
    assertThat(response.getContentAsString())
        .contains("\"code\":\"INTERNAL_ERROR\"")
        .doesNotContain("secret internal detail");
  }

  @Test
  void aCommittedResponseIsNotWrittenAgainAndTheExceptionIsRethrown() throws Exception {
    response = spy(new MockHttpServletResponse());
    doReturn(true).when(response).isCommitted();
    CannotGetJdbcConnectionException failure = new CannotGetJdbcConnectionException("late");

    assertThatThrownBy(() -> run(throwing(failure))).isSameAs(failure);

    assertThat(response.getContentAsString()).isEmpty();
    verify(response, never()).reset();
  }

  // ---- 건드리지 않는 것 ----

  @Test
  void authenticationAndAccessDeniedExceptionsPassThroughUntouched() throws Exception {
    BadCredentialsException authentication = new BadCredentialsException("no");
    AccessDeniedException denied = new AccessDeniedException("no");

    assertThatThrownBy(() -> run(throwing(authentication))).isSameAs(authentication);
    assertThatThrownBy(() -> run(throwing(denied))).isSameAs(denied);
    assertThat(response.getContentAsString()).isEmpty();
  }

  @Test
  void clientConnectionErrorsPassThroughUntouched() throws Exception {
    IOException broken = new IOException("Broken pipe");

    assertThatThrownBy(() -> run(throwing(broken))).isSameAs(broken);
    assertThat(response.getContentAsString()).isEmpty();
  }

  @Test
  void aNormalRequestIsNotTouched() throws Exception {
    run((req, res) -> ((MockHttpServletResponse) res).setStatus(204));

    assertThat(response.getStatus()).isEqualTo(204);
  }

  // ---- 지표 ----

  private double failures(String cause) {
    var counter = registry.find("mairor.session.failures").tag("cause", cause).counter();
    return counter == null ? 0 : counter.count();
  }

  @Test
  void eachFailureIsCountedByItsCause() throws Exception {
    run(throwing(new CannotGetJdbcConnectionException("pool")));
    response = new MockHttpServletResponse();
    run(throwing(new CannotGetJdbcConnectionException("pool")));
    response = new MockHttpServletResponse();
    run(throwing(new UnreadableSessionException("bad", new IllegalStateException())));
    response = new MockHttpServletResponse();
    run(throwing(new IllegalStateException("bug")));

    assertThat(failures("store_unavailable")).isEqualTo(2);
    assertThat(failures("corrupted_session")).isEqualTo(1);
    assertThat(failures("unexpected")).isEqualTo(1);
  }

  @Test
  void aCommittedResponseIsStillCounted() {
    response = spy(new MockHttpServletResponse());
    doReturn(true).when(response).isCommitted();

    assertThatThrownBy(() -> run(throwing(new CannotGetJdbcConnectionException("late"))))
        .isInstanceOf(CannotGetJdbcConnectionException.class);

    assertThat(failures("store_unavailable")).isEqualTo(1);
  }

  @Test
  void passThroughExceptionsAreNotCounted() {
    assertThatThrownBy(() -> run(throwing(new IOException("Broken pipe"))))
        .isInstanceOf(IOException.class);

    assertThat(registry.getMeters()).isEmpty();
  }
}
