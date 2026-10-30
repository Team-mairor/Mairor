package com.mairor.backend.common.security;

import java.time.Duration;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

/** 세션 수명 정책 빈. 흩어진 세 설정(서버 유휴 만료, 쿠키 최대 수명, 절대 만료)을 읽어 관계를 검증한다. 어긋나거나 빠져 있으면 앱이 기동하지 않는다. */
@Configuration
public class SessionLifetimeConfig {

  @Bean
  SessionLifetimePolicy sessionLifetimePolicy(
      SessionLifetimeProperties properties, Environment environment) {
    Binder binder = Binder.get(environment);
    Duration idleTimeout = required(binder, "spring.session.timeout");
    Duration cookieMaxAge = required(binder, "server.servlet.session.cookie.max-age");
    return new SessionLifetimePolicy(cookieMaxAge, idleTimeout, properties.absoluteTimeout());
  }

  private static Duration required(Binder binder, String name) {
    return binder
        .bind(name, Duration.class)
        .orElseThrow(() -> new IllegalStateException(name + " 설정이 필요합니다."));
  }
}
