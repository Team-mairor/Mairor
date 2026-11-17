package com.mairor.backend.users.support;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

/** Login attempt limiter and BCrypt gate configuration. */
@Configuration
public class LoginConfig {

  private static final Logger log = LoggerFactory.getLogger(LoginConfig.class);

  @Bean
  @ConditionalOnProperty(
      prefix = "app.login",
      name = "attempt-store",
      havingValue = "memory",
      matchIfMissing = true)
  LoginAttemptLimiter loginAttemptLimiter(LoginProperties properties) {
    log.warn("로그인 시도 제한을 인메모리로 처리합니다. 서버 1대에서만 정확하고 재시작하면 횟수와 잠금이 초기화됩니다.");
    return new InMemoryLoginAttemptLimiter(
        properties.maxFailures(),
        properties.lockDuration(),
        properties.attemptTtl(),
        properties.maxEntries(),
        log::warn);
  }

  @Bean
  @ConditionalOnProperty(prefix = "app.login", name = "attempt-store", havingValue = "redis")
  LoginAttemptLimiter redisLoginAttemptLimiter(
      StringRedisTemplate redis, LoginProperties properties) {
    return new RedisLoginAttemptLimiter(redis, properties);
  }

  @Bean
  LoginHashGate loginHashGate(LoginProperties properties) {
    return new LoginHashGate(properties.maxConcurrentHashes());
  }
}
