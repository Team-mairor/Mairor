package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.support.LoginAttemptLimiter.Allowed;
import com.mairor.backend.users.support.LoginAttemptLimiter.Locked;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** {@code application.yml} 의 기본값이 바인딩되고 인메모리 제한기와 BCrypt 게이트 빈이 만들어지는지 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
class LoginConfigTest {

  @Autowired private LoginProperties properties;
  @Autowired private LoginAttemptLimiter limiter;
  @Autowired private LoginHashGate gate;

  @Test
  void defaultsAreBound() {
    assertThat(properties.maxFailures()).isEqualTo(3);
    assertThat(properties.lockDuration()).isEqualTo(Duration.ofSeconds(30));
    assertThat(properties.attemptTtl()).isEqualTo(Duration.ofMinutes(15));
    assertThat(properties.maxEntries()).isEqualTo(10_000);
    assertThat(properties.maxConcurrentHashes()).isEqualTo(4);
  }

  @Test
  void limiterIsTheInMemoryOneConfiguredWithTheProperties() {
    assertThat(limiter).isInstanceOf(InMemoryLoginAttemptLimiter.class);
    Instant now = Instant.parse("2026-10-29T00:00:00Z");

    // 설정의 3회에서 잠긴다
    for (int i = 0; i < 3; i++) {
      var ticket = ((Allowed) limiter.tryAcquire("config-test@example.com", now)).ticket();
      limiter.fail(ticket, now);
    }
    assertThat(limiter.tryAcquire("config-test@example.com", now)).isInstanceOf(Locked.class);
    // 설정의 30초가 지나면 풀린다
    assertThat(limiter.tryAcquire("config-test@example.com", now.plusSeconds(30)))
        .isInstanceOf(Allowed.class);
  }

  @Test
  void hashGateAllowsTheConfiguredConcurrency() {
    assertThat(gate.availablePermits()).isEqualTo(4);
  }
}
