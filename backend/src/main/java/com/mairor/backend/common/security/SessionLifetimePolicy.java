package com.mairor.backend.common.security;

import java.time.Duration;
import java.time.Instant;

/**
 * 세션 수명 정책. 서버 세션 유휴 만료, 쿠키 최대 수명, 절대 만료를 한곳에 모아 필터가 쓴다. 세 값은 {@code 쿠키 최대 수명 ≤ 유휴 만료 ≤ 절대 만료} 를
 * 지켜야 한다. 서버 세션이 쿠키보다 먼저 사라지면 쿠키를 길게 둘 이유가 없고, 유휴 만료가 절대 만료보다 길면 절대 만료가 의미를 잃기 때문이다.
 *
 * @param cookieMaxAge 쿠키 {@code Max-Age} 의 상한. 갱신할 때 절대 만료까지 남은 시간이 더 짧으면 그 값을 쓴다
 * @param idleTimeout 마지막 인증 요청으로부터 서버 세션이 유지되는 시간
 * @param absoluteTimeout 로그인 성공 시점으로부터 세션이 유지되는 최대 시간
 */
public record SessionLifetimePolicy(
    Duration cookieMaxAge, Duration idleTimeout, Duration absoluteTimeout) {

  public SessionLifetimePolicy {
    requirePositive("쿠키 최대 수명(server.servlet.session.cookie.max-age)", cookieMaxAge);
    requirePositive("유휴 만료(spring.session.timeout)", idleTimeout);
    requirePositive("절대 만료(app.session.absolute-timeout)", absoluteTimeout);
    if (cookieMaxAge.compareTo(idleTimeout) > 0) {
      throw new IllegalArgumentException(
          "쿠키 최대 수명(" + cookieMaxAge + ")은 유휴 만료(" + idleTimeout + ")보다 길 수 없습니다.");
    }
    if (idleTimeout.compareTo(absoluteTimeout) > 0) {
      throw new IllegalArgumentException(
          "유휴 만료(" + idleTimeout + ")는 절대 만료(" + absoluteTimeout + ")보다 길 수 없습니다.");
    }
  }

  /** 로그인 시각 기준 절대 만료 시각. */
  public Instant absoluteExpiryOf(Instant authenticatedAt) {
    return authenticatedAt.plus(absoluteTimeout);
  }

  /** 절대 만료 시각에 닿았거나 지났으면 {@code true}. 정확히 닿은 순간도 만료다. */
  public boolean isAbsolutelyExpired(Instant authenticatedAt, Instant now) {
    return !now.isBefore(absoluteExpiryOf(authenticatedAt));
  }

  private static void requirePositive(String name, Duration value) {
    if (value == null || value.isZero() || value.isNegative()) {
      throw new IllegalArgumentException(name + " 은 0보다 길어야 합니다: " + value);
    }
  }
}
