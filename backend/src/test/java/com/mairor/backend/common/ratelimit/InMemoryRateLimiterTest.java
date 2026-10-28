package com.mairor.backend.common.ratelimit;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class InMemoryRateLimiterTest extends RateLimiterContract {

  @Override
  protected RateLimiter create(int limit, Duration window) {
    return new InMemoryRateLimiter(limit, window);
  }

  @Test
  void rejectsAnInvalidLimit() {
    assertThatThrownBy(() -> new InMemoryRateLimiter(0, Duration.ofMinutes(1)))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void rejectsAnInvalidWindow() {
    assertThatThrownBy(() -> new InMemoryRateLimiter(1, Duration.ZERO))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new InMemoryRateLimiter(1, Duration.ofSeconds(-1)))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
