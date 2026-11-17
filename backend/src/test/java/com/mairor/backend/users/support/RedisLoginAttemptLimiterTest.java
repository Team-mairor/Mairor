package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.testsupport.RedisTestServer;
import com.mairor.backend.users.support.LoginAttemptLimiter.Allowed;
import java.time.Duration;
import org.junit.jupiter.api.Test;

/** Redis 구현이 인메모리와 같은 계약을 지키는지 실제 Redis 로 확인한다. 키 이름이 고정이라 만들 때마다 Redis 를 비운다. */
class RedisLoginAttemptLimiterTest extends LoginAttemptLimiterContract {

  @Override
  protected LoginAttemptLimiter create(
      int maxFailures, Duration lockDuration, Duration attemptTtl, int maxEntries) {
    RedisTestServer.flush();
    return new RedisLoginAttemptLimiter(
        RedisTestServer.template(),
        new LoginProperties(maxFailures, lockDuration, attemptTtl, maxEntries, 4));
  }

  /** 시도 도중 서버가 죽어 끝나지 않은 시도가 남아도, attempt-ttl 이 지나면 그 이메일은 다시 로그인할 수 있다. */
  @Test
  void anAttemptLeftOpenByACrashedServerIsForgottenAfterTheAttemptTtl() {
    LoginAttemptLimiter limiter = create(1, Duration.ofSeconds(30), Duration.ofMinutes(15), 1_000);
    acquire(limiter, "a@x.com", T0);

    assertThat(limiter.tryAcquire("a@x.com", T0.plus(Duration.ofHours(1))))
        .isInstanceOf(Allowed.class);
  }
}
