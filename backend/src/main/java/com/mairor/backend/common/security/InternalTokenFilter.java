package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 내부 API({@code /v1/internal/**}) 요청의 {@value #HEADER} 헤더를 공유 토큰과 비교한다. 없거나 다르면 401 {@code
 * UNAUTHORIZED}이고, 토큰이 설정되지 않았으면 내부 API 는 전부 401 이다.
 *
 * <p>내부 API 는 사람(운영자 curl)과 서버(AI 콜백)가 부르므로 세션·CSRF·Origin 검사 대신 이 필터가 지킨다. 비교는 상수 시간이고 토큰 값은 로그에
 * 남기지 않는다. {@code @Component}로 만들면 서블릿 컨테이너에 한 번 더 등록되므로 {@link SecurityConfig}가 만들어 보안 체인에만 끼운다.
 */
public class InternalTokenFilter extends OncePerRequestFilter {

  public static final String HEADER = "X-Internal-Token";

  private static final Logger log = LoggerFactory.getLogger(InternalTokenFilter.class);

  private final RequestMatcher internalRequests;
  private final InternalApiProperties properties;
  private final ErrorResponseWriter errorWriter;

  public InternalTokenFilter(
      RequestMatcher internalRequests,
      InternalApiProperties properties,
      ErrorResponseWriter errorWriter) {
    this.internalRequests = internalRequests;
    this.properties = properties;
    this.errorWriter = errorWriter;
    if (!properties.configured()) {
      log.warn("app.internal.token(INTERNAL_API_TOKEN)이 비어 있어 내부 API 는 모든 요청을 거절합니다.");
    }
  }

  @Override
  protected boolean shouldNotFilter(HttpServletRequest request) {
    return !internalRequests.matches(request);
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    if (!matches(request.getHeader(HEADER))) {
      log.info("내부 API 토큰 불일치: {} {}", request.getMethod(), request.getRequestURI());
      errorWriter.write(response, ErrorCode.UNAUTHORIZED);
      return;
    }
    chain.doFilter(request, response);
  }

  private boolean matches(String presented) {
    if (!properties.configured() || presented == null) {
      return false;
    }
    return MessageDigest.isEqual(
        presented.getBytes(StandardCharsets.UTF_8),
        properties.token().getBytes(StandardCharsets.UTF_8));
  }
}
