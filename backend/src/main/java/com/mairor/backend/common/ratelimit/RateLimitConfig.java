package com.mairor.backend.common.ratelimit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * 공개 API 묶음마다 따로 세는 IP 요청 제한. 같은 타입 빈이 넷이라 주입하는 곳은 빈 이름({@code @Qualifier})으로 고른다. 인메모리와 Redis 구현은
 * 설정으로 하나만 뜨고, 같은 이름을 쓴다.
 */
@Configuration
public class RateLimitConfig {

  private static final Logger log = LoggerFactory.getLogger(RateLimitConfig.class);

  /** 이메일 중복 확인(API-USERS-011). 키는 클라이언트 IP. */
  @Bean
  @ConditionalOnProperty(
      prefix = "app.rate-limit",
      name = "store-type",
      havingValue = "memory",
      matchIfMissing = true)
  RateLimiter emailAvailabilityRateLimiter(RateLimitProperties properties) {
    log.warn("요청 제한을 인메모리로 처리합니다. 서버 1대에서만 정확하고 재시작하면 카운트가 초기화됩니다.");
    RateLimitProperties.Rule rule = properties.emailAvailability();
    return new InMemoryRateLimiter(rule.limit(), rule.window());
  }

  @Bean("emailAvailabilityRateLimiter")
  @ConditionalOnProperty(prefix = "app.rate-limit", name = "store-type", havingValue = "redis")
  RateLimiter redisEmailAvailabilityRateLimiter(
      RateLimitProperties properties, StringRedisTemplate redis) {
    RateLimitProperties.Rule rule = properties.emailAvailability();
    return new RedisRateLimiter(redis, "email-availability", rule.limit(), rule.window());
  }

  /**
   * 가입 이메일 인증번호 발송. 키는 클라이언트 IP. 이메일마다 쿨다운·시간당 횟수 제한이 따로 있지만, 한 곳에서 여러 이메일로 보내 메일을 쏟아내는 것은 이쪽에서
   * 막는다.
   */
  @Bean
  @ConditionalOnProperty(
      prefix = "app.rate-limit",
      name = "store-type",
      havingValue = "memory",
      matchIfMissing = true)
  RateLimiter emailVerificationRateLimiter(RateLimitProperties properties) {
    RateLimitProperties.Rule rule = properties.emailVerification();
    return new InMemoryRateLimiter(rule.limit(), rule.window());
  }

  @Bean("emailVerificationRateLimiter")
  @ConditionalOnProperty(prefix = "app.rate-limit", name = "store-type", havingValue = "redis")
  RateLimiter redisEmailVerificationRateLimiter(
      RateLimitProperties properties, StringRedisTemplate redis) {
    RateLimitProperties.Rule rule = properties.emailVerification();
    return new RedisRateLimiter(redis, "email-verification", rule.limit(), rule.window());
  }

  /**
   * 비밀번호 재설정 인증번호 발송(API-USERS-008). 키는 클라이언트 IP. 이메일마다 쿨다운·시간당 횟수 제한이 따로 있지만, 한 곳에서 여러 이메일로 요청을
   * 쏟아내는 것은 이쪽에서 막는다. 가입 인증과 따로 센다.
   */
  @Bean
  @ConditionalOnProperty(
      prefix = "app.rate-limit",
      name = "store-type",
      havingValue = "memory",
      matchIfMissing = true)
  RateLimiter passwordResetRateLimiter(RateLimitProperties properties) {
    RateLimitProperties.Rule rule = properties.passwordReset();
    return new InMemoryRateLimiter(rule.limit(), rule.window());
  }

  @Bean("passwordResetRateLimiter")
  @ConditionalOnProperty(prefix = "app.rate-limit", name = "store-type", havingValue = "redis")
  RateLimiter redisPasswordResetRateLimiter(
      RateLimitProperties properties, StringRedisTemplate redis) {
    RateLimitProperties.Rule rule = properties.passwordReset();
    return new RedisRateLimiter(redis, "password-reset", rule.limit(), rule.window());
  }

  /** Google 로그인 시작(API-USERS-006). 키는 클라이언트 IP. 시작마다 인가 요청을 저장하므로 한 곳에서 저장소를 채우는 것을 막는다. */
  @Bean
  @ConditionalOnProperty(
      prefix = "app.rate-limit",
      name = "store-type",
      havingValue = "memory",
      matchIfMissing = true)
  RateLimiter googleLoginRateLimiter(RateLimitProperties properties) {
    RateLimitProperties.Rule rule = properties.googleLogin();
    return new InMemoryRateLimiter(rule.limit(), rule.window());
  }

  @Bean("googleLoginRateLimiter")
  @ConditionalOnProperty(prefix = "app.rate-limit", name = "store-type", havingValue = "redis")
  RateLimiter redisGoogleLoginRateLimiter(
      RateLimitProperties properties, StringRedisTemplate redis) {
    RateLimitProperties.Rule rule = properties.googleLogin();
    return new RedisRateLimiter(redis, "google-login", rule.limit(), rule.window());
  }
}
