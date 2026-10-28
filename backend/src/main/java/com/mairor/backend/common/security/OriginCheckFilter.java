package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.URISyntaxException;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 허용 Origin 검증. 세션이 없어 CSRF 토큰을 쓸 수 없는 요청을 "JSON 요청 + 허용 Origin"으로 보호한다.
 *
 * <p>보호 대상 요청은 {@code Origin} 헤더가 정확히 하나이고 허용 목록에 있어야 통과하고, 아니면 403 {@code FORBIDDEN}이다. 스킴·호스트·포트로
 * 나눠 비교한다(기본 포트·끝 {@code /}·대소문자 무시). 대상이 아닌 요청은 건드리지 않는다.
 *
 * <p>{@code Origin}은 curl·봇이 위조할 수 있어 브라우저의 교차 사이트 요청만 막는다. {@code @Component}로 만들면 서블릿 컨테이너에 한 번 더
 * 등록되므로 {@link SecurityConfig}가 만들어 보안 체인에만 끼운다.
 */
public class OriginCheckFilter extends OncePerRequestFilter {

  private static final Logger log = LoggerFactory.getLogger(OriginCheckFilter.class);
  private static final int LOGGED_VALUE_LIMIT = 100;

  private final List<RequestMatcher> protectedRequests;
  private final Set<String> allowedOrigins;
  private final ErrorResponseWriter errorWriter;

  /**
   * @throws IllegalArgumentException 허용 목록에 Origin 형식이 아닌 값이 있을 때 (설정 오류는 시작 단계에서 드러나게 한다)
   */
  public OriginCheckFilter(
      List<RequestMatcher> protectedRequests,
      Collection<String> allowedOrigins,
      ErrorResponseWriter errorWriter) {
    this.protectedRequests = List.copyOf(protectedRequests);
    this.allowedOrigins =
        allowedOrigins.stream()
            .map(OriginCheckFilter::requireValidOrigin)
            .collect(Collectors.toUnmodifiableSet());
    this.errorWriter = errorWriter;
  }

  @Override
  protected void doFilterInternal(
      HttpServletRequest request, HttpServletResponse response, FilterChain chain)
      throws ServletException, IOException {
    if (protectedRequests.stream().noneMatch(matcher -> matcher.matches(request))) {
      chain.doFilter(request, response);
      return;
    }
    if (!isAllowed(request)) {
      log.debug(
          "허용되지 않은 Origin: {} {} origin={}",
          request.getMethod(),
          request.getRequestURI(),
          loggable(Collections.list(request.getHeaders(HttpHeaders.ORIGIN))));
      errorWriter.write(response, ErrorCode.FORBIDDEN);
      return;
    }
    chain.doFilter(request, response);
  }

  private boolean isAllowed(HttpServletRequest request) {
    List<String> values = Collections.list(request.getHeaders(HttpHeaders.ORIGIN));
    if (values.size() != 1) {
      return false;
    }
    String normalized = normalize(values.get(0));
    return normalized != null && allowedOrigins.contains(normalized);
  }

  private static String requireValidOrigin(String configured) {
    String normalized = normalize(configured);
    if (normalized == null) {
      throw new IllegalArgumentException(
          "허용 Origin 형식이 올바르지 않습니다 (예: https://example.com:3000): " + configured);
    }
    return normalized;
  }

  /**
   * {@code 스킴://호스트[:포트]} 형태의 Origin을 비교용 문자열로 바꾼다. 기본 포트(http 80, https 443)와 끝의 {@code /}는 없앤다.
   *
   * @return 형식이 올바르지 않으면 {@code null}
   */
  static String normalize(String origin) {
    if (origin == null) {
      return null;
    }
    URI uri;
    try {
      uri = new URI(origin.strip());
    } catch (URISyntaxException e) {
      return null;
    }
    String scheme = uri.getScheme() == null ? null : uri.getScheme().toLowerCase(Locale.ROOT);
    boolean httpOrHttps = "http".equals(scheme) || "https".equals(scheme);
    boolean pathOnlyRoot =
        uri.getRawPath() == null || uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath());
    if (!httpOrHttps
        || uri.getHost() == null
        || uri.getRawUserInfo() != null
        || !pathOnlyRoot
        || uri.getRawQuery() != null
        || uri.getRawFragment() != null) {
      return null;
    }
    int port = uri.getPort();
    boolean defaultPort =
        port == -1
            || (port == 80 && "http".equals(scheme))
            || (port == 443 && "https".equals(scheme));
    return scheme
        + "://"
        + uri.getHost().toLowerCase(Locale.ROOT)
        + (defaultPort ? "" : ":" + port);
  }

  /** 요청이 보낸 값은 로그 줄을 깨뜨릴 수 있어(줄바꿈 등) 출력 가능한 문자만 남기고 길이를 제한한다. */
  private static String loggable(List<String> values) {
    String joined = String.join(",", values).replaceAll("[^\\x20-\\x7E]", "?");
    return joined.length() > LOGGED_VALUE_LIMIT
        ? joined.substring(0, LOGGED_VALUE_LIMIT) + "…"
        : joined;
  }
}
