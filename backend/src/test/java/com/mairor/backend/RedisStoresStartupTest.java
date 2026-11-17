package com.mairor.backend;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.common.ratelimit.RateLimiter;
import com.mairor.backend.common.ratelimit.RedisRateLimiter;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.EmailVerificationStoreConfig;
import com.mairor.backend.users.support.LoginAttemptLimiter;
import com.mairor.backend.users.support.RedisEmailVerificationStore;
import com.mairor.backend.users.support.RedisLoginAttemptLimiter;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;

/**
 * 운영처럼 인증 임시 상태를 모두 Redis 에 두어도 서버가 뜨고, 주입하는 곳이 이름으로 찾는 빈이 Redis 구현인지 확인한다. 다른 테스트는 서로의 카운트가 섞이지 않게
 * 인메모리를 쓰므로, 운영 설정의 빈 구성은 여기서만 확인된다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "app.login.attempt-store=redis",
      "app.verification-store.type=redis",
      "app.password-reset.lock-store=redis",
      "app.rate-limit.store-type=redis",
      "app.oauth.google.state-store=redis"
    })
class RedisStoresStartupTest {

  @Autowired private ApplicationContext context;

  @Test
  void everyRateLimiterThatIsInjectedByNameIsTheRedisOne() {
    for (String name :
        List.of(
            "emailAvailabilityRateLimiter",
            "emailVerificationRateLimiter",
            "passwordResetRateLimiter",
            "googleLoginRateLimiter")) {
      assertThat(context.getBean(name, RateLimiter.class))
          .as(name)
          .isInstanceOf(RedisRateLimiter.class);
    }
  }

  @Test
  void verificationStoresAndTheLoginLimiterAreTheRedisOnes() {
    for (String name :
        List.of(EmailVerificationStoreConfig.SIGNUP, EmailVerificationStoreConfig.PASSWORD_RESET)) {
      assertThat(context.getBean(name, EmailVerificationStore.class))
          .as(name)
          .isInstanceOf(RedisEmailVerificationStore.class);
    }
    assertThat(context.getBean(LoginAttemptLimiter.class))
        .isInstanceOf(RedisLoginAttemptLimiter.class);
  }
}
