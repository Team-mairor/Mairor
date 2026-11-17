package com.mairor.backend.users.support;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

/** Selects the password reset lock implementation. */
@Configuration
public class PasswordResetLockConfig {

  private static final Logger log = LoggerFactory.getLogger(PasswordResetLockConfig.class);

  @Bean
  @ConditionalOnProperty(
      prefix = "app.password-reset",
      name = "lock-store",
      havingValue = "memory",
      matchIfMissing = true)
  PasswordResetLocks inMemoryPasswordResetLocks() {
    log.warn("비밀번호 재설정 잠금을 인메모리로 처리합니다. 서버 여러 대에서는 요청 동시성이 공유되지 않습니다.");
    return new PasswordResetLocks();
  }

  @Bean
  @ConditionalOnProperty(prefix = "app.password-reset", name = "lock-store", havingValue = "redis")
  PasswordResetLocks redisPasswordResetLocks(StringRedisTemplate redis) {
    return new PasswordResetLocks(redis);
  }
}
