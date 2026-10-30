package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class SessionLifetimePolicyTest {

  private static final Duration THREE_DAYS = Duration.ofDays(3);
  private static final Duration THIRTY_DAYS = Duration.ofDays(30);

  @Test
  void acceptsTheDocumentedValues() {
    SessionLifetimePolicy policy = new SessionLifetimePolicy(THREE_DAYS, THREE_DAYS, THIRTY_DAYS);

    assertThat(policy.cookieMaxAge()).isEqualTo(THREE_DAYS);
    assertThat(policy.idleTimeout()).isEqualTo(THREE_DAYS);
    assertThat(policy.absoluteTimeout()).isEqualTo(THIRTY_DAYS);
  }

  @Test
  void acceptsACookieShorterThanTheIdleTimeout() {
    new SessionLifetimePolicy(Duration.ofDays(1), THREE_DAYS, THIRTY_DAYS);
  }

  @Test
  void rejectsACookieLongerThanTheIdleTimeout() {
    assertThatThrownBy(() -> new SessionLifetimePolicy(Duration.ofDays(4), THREE_DAYS, THIRTY_DAYS))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("쿠키 최대 수명");
  }

  @Test
  void rejectsAnIdleTimeoutLongerThanTheAbsoluteTimeout() {
    assertThatThrownBy(
            () -> new SessionLifetimePolicy(THREE_DAYS, Duration.ofDays(31), THIRTY_DAYS))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("유휴 만료");
  }

  @Test
  void rejectsZeroNegativeOrMissingValues() {
    assertThatThrownBy(() -> new SessionLifetimePolicy(Duration.ZERO, THREE_DAYS, THIRTY_DAYS))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> new SessionLifetimePolicy(THREE_DAYS, Duration.ofDays(-3), THIRTY_DAYS))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new SessionLifetimePolicy(THREE_DAYS, THREE_DAYS, null))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void theAbsoluteExpiryIsTheLoginTimePlusTheAbsoluteTimeout() {
    SessionLifetimePolicy policy = new SessionLifetimePolicy(THREE_DAYS, THREE_DAYS, THIRTY_DAYS);
    Instant loggedIn = Instant.parse("2026-10-01T00:00:00Z");

    assertThat(policy.absoluteExpiryOf(loggedIn)).isEqualTo(Instant.parse("2026-10-31T00:00:00Z"));
  }

  @Test
  void aSessionIsExpiredFromTheExactAbsoluteExpiryOn() {
    SessionLifetimePolicy policy = new SessionLifetimePolicy(THREE_DAYS, THREE_DAYS, THIRTY_DAYS);
    Instant loggedIn = Instant.parse("2026-10-01T00:00:00Z");
    Instant expiry = policy.absoluteExpiryOf(loggedIn);

    assertThat(policy.isAbsolutelyExpired(loggedIn, expiry.minusMillis(1))).isFalse();
    assertThat(policy.isAbsolutelyExpired(loggedIn, expiry)).isTrue();
    assertThat(policy.isAbsolutelyExpired(loggedIn, expiry.plusSeconds(1))).isTrue();
  }
}
