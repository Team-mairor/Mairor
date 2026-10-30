package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorResponseWriter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.session.web.http.CookieSerializer;

/**
 * {@link SessionStoreFailureFilter} 를 서블릿 필터로 등록한다. Spring Session 의 필터(기본 순서 {@code
 * HIGHEST_PRECEDENCE + 50}) 보다 바깥에 있어야 응답을 커밋할 때의 세션 저장·삭제 실패를 받는다. 필터를 빈으로 직접 노출하지 않고 등록 빈으로만 만들어
 * 두 번 등록되지 않게 한다.
 */
@Configuration
public class SessionStoreFailureConfig {

  /** Spring Session 필터({@code HIGHEST_PRECEDENCE + 50}) 보다 앞선다. */
  static final int ORDER = Ordered.HIGHEST_PRECEDENCE + 10;

  @Bean
  FilterRegistrationBean<SessionStoreFailureFilter> sessionStoreFailureFilter(
      ErrorResponseWriter errorWriter, CookieSerializer cookieSerializer, SessionMetrics metrics) {
    FilterRegistrationBean<SessionStoreFailureFilter> registration =
        new FilterRegistrationBean<>(
            new SessionStoreFailureFilter(errorWriter, cookieSerializer, metrics));
    registration.setOrder(ORDER);
    return registration;
  }
}
