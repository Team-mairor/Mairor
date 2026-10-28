package com.mairor.backend.common.ratelimit;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.time.Clock;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** 설정 기본값이 바인딩되고 요청 제한 빈과 {@code Clock} 빈이 만들어지는지 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
class RateLimitConfigTest {

  @Autowired private RateLimitProperties properties;
  @Autowired private RateLimiter emailAvailabilityRateLimiter;
  @Autowired private Clock clock;

  @Test
  void emailAvailabilityDefaultsAreBound() {
    assertThat(properties.emailAvailability().limit()).isEqualTo(30);
    assertThat(properties.emailAvailability().window()).isEqualTo(Duration.ofMinutes(1));
  }

  @Test
  void emailAvailabilityLimiterEnforcesTheConfiguredLimit() {
    var now = clock.instant();

    for (int i = 0; i < 30; i++) {
      assertThat(emailAvailabilityRateLimiter.tryAcquire("config-test-ip", now).allowed()).isTrue();
    }
    assertThat(emailAvailabilityRateLimiter.tryAcquire("config-test-ip", now).allowed()).isFalse();
  }
}
