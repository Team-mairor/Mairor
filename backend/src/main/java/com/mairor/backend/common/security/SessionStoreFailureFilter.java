package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import com.mairor.backend.common.error.StoreFailure;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.CookieSerializer.CookieValue;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 세션 필터·시큐리티 필터 단계에서 터진 예외를 공통 오류 응답으로 바꾸는 경계. 이 단계는 MVC 밖이라 {@code GlobalExceptionHandler} 가 받지
 * 못하고, 처리하지 않으면 컨테이너의 HTML 오류 페이지가 나간다. 세션을 읽는 일(인증 정보 조회)과 저장하는 일(응답을 커밋할 때 저장·삭제)이 모두 이 단계에서
 * 일어난다.
 *
 * <p>Spring Session 의 필터보다 <b>바깥</b>에 둔다. 그래야 응답을 커밋할 때 하는 세션 저장·삭제의 실패도 받는다. 아직 커밋되지 않은 응답은 지금까지 쓴
 * 내용(성공 본문)을 버리고 오류로 바꾼다. 세션을 저장하지 못했는데 로그인 성공 본문이 나가면 안 되기 때문이다.
 *
 * <p>원인을 구분한다. 모든 예외를 같게 다루지 않는다.
 *
 * <ul>
 *   <li><b>저장소 장애</b>(연결 실패·연결 풀 소진·일시적 장애·쿼리 시간 초과, 기준은 {@link StoreFailure}): {@code 503
 *       SERVICE_UNAVAILABLE}. 인증 실패(401)로 바꾸지 않는다. 세션은 DB 에 그대로 있을 수 있다.
 *   <li><b>손상된 세션</b>(저장된 값을 읽지 못함, {@link UnreadableSessionException}): {@code 401} 과 세션 쿠키 만료. 다시
 *       로그인하게 하고, 같은 쿠키로 계속 실패하지 않게 한다. 새 값을 저장하지 못하는 직렬화 실패는 서버 버그라서 여기에 넣지 않는다.
 *   <li>그 밖의 예외: {@code 500 INTERNAL_ERROR}. 잘못된 SQL·스키마 불일치·제약 위반 같은 DB 오류도 서버 문제라서 여기에 속한다.
 * </ul>
 *
 * <p>이미 커밋된 응답은 다시 쓰지 않는다. 기록만 남기고 예외를 그대로 던져 컨테이너가 연결을 정리하게 한다. 인증·인가 예외와 클라이언트 연결 오류({@link
 * IOException})는 이 필터의 일이 아니므로 건드리지 않는다.
 */
public class SessionStoreFailureFilter extends OncePerRequestFilter {

  private static final Logger log = LoggerFactory.getLogger(SessionStoreFailureFilter.class);

  /** 실패 원인 분류. */
  enum Cause {
    STORE_UNAVAILABLE,
    CORRUPTED_SESSION,
    UNEXPECTED
  }

  private final ErrorResponseWriter errorWriter;
  private final CookieSerializer cookieSerializer;
  private final SessionMetrics metrics;

  public SessionStoreFailureFilter(
      ErrorResponseWriter errorWriter, CookieSerializer cookieSerializer, SessionMetrics metrics) {
    this.errorWriter = errorWriter;
    this.cookieSerializer = cookieSerializer;
    this.metrics = metrics;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    try {
      chain.doFilter(request, response);
    } catch (IOException | AuthenticationException | AccessDeniedException e) {
      throw e;
    } catch (ServletException | RuntimeException e) {
      handle(request, response, e);
    }
  }

  private void handle(HttpServletRequest request, HttpServletResponse response, Exception e)
      throws ServletException, IOException {
    Cause cause = classify(e);
    metrics.failure(cause);
    if (response.isCommitted()) {
      log.error("응답이 이미 커밋되어 오류 응답을 쓰지 못했습니다. 원인 분류: {}", cause, e);
      throw rethrow(e);
    }
    response.reset();
    switch (cause) {
      case STORE_UNAVAILABLE -> {
        log.error("세션 저장소를 사용하지 못했습니다.", e);
        errorWriter.write(response, ErrorCode.SERVICE_UNAVAILABLE);
      }
      case CORRUPTED_SESSION -> {
        log.warn("저장된 세션을 읽지 못해 세션 쿠키를 만료시킵니다: {}", e.getClass().getSimpleName());
        cookieSerializer.writeCookieValue(new CookieValue(request, response, ""));
        errorWriter.write(response, ErrorCode.UNAUTHORIZED);
      }
      case UNEXPECTED -> {
        log.error("필터 단계에서 처리하지 못한 예외", e);
        errorWriter.write(response, ErrorCode.INTERNAL_ERROR);
      }
    }
  }

  static Cause classify(Throwable e) {
    boolean store = false;
    for (Throwable t = e; t != null; t = t.getCause() == t ? null : t.getCause()) {
      if (t instanceof UnreadableSessionException) {
        return Cause.CORRUPTED_SESSION;
      }
      if (StoreFailure.isUnavailable(t)) {
        store = true;
      }
    }
    return store ? Cause.STORE_UNAVAILABLE : Cause.UNEXPECTED;
  }

  private static ServletException rethrow(Exception e) throws ServletException {
    if (e instanceof RuntimeException runtime) {
      throw runtime;
    }
    throw (ServletException) e;
  }
}
