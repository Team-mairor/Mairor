package com.mairor.backend.users.support;

import java.time.Clock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * 인증 임시 상태 저장소 구현을 고른다 ({@code app.verification-store.type}). 개발 기본값은 {@code memory}이고 운영 기본값은
 * {@code redis}다.
 *
 * <p>저장소는 용도마다 하나씩, 이름이 다른 빈 두 개다. 가입 이메일 인증({@link #SIGNUP})과 비밀번호 재설정({@link #PASSWORD_RESET})이
 * 인증번호·토큰·발송 제한을 공유하지 않는다. 같은 타입 빈이 둘이라 주입하는 곳마다 {@code @Qualifier} 로 이름을 지정해야 하고, 지정하지 않으면 시작할 때
 * 실패한다(어느 쪽인지 모른 채 쓰는 일을 막는다).
 */
@Configuration
public class EmailVerificationStoreConfig {

  /** 가입 이메일 소유 확인용 저장소의 빈 이름. */
  public static final String SIGNUP = "signupVerificationStore";

  /** 비밀번호 재설정용 저장소의 빈 이름. */
  public static final String PASSWORD_RESET = "passwordResetStore";

  private static final Logger log = LoggerFactory.getLogger(EmailVerificationStoreConfig.class);

  @Bean(SIGNUP)
  @ConditionalOnProperty(
      prefix = "app.verification-store",
      name = "type",
      havingValue = "memory",
      matchIfMissing = true)
  EmailVerificationStore signupVerificationStore(EmailVerificationProperties properties) {
    log.warn("가입 이메일 인증 임시 상태를 인메모리에 둡니다. 서버 1대에서만 정확하고 재시작하면 진행 중인 인증이 사라집니다.");
    return new InMemoryEmailVerificationStore(
        properties.resendCooldown(), properties.hourlyLimit());
  }

  @Bean(PASSWORD_RESET)
  @ConditionalOnProperty(
      prefix = "app.verification-store",
      name = "type",
      havingValue = "memory",
      matchIfMissing = true)
  EmailVerificationStore passwordResetStore(PasswordResetProperties properties) {
    log.warn("비밀번호 재설정 임시 상태를 인메모리에 둡니다. 서버 1대에서만 정확하고 재시작하면 진행 중인 재설정이 사라집니다.");
    return new InMemoryEmailVerificationStore(
        properties.resendCooldown(), properties.hourlyLimit());
  }

  @Bean(SIGNUP)
  @ConditionalOnProperty(prefix = "app.verification-store", name = "type", havingValue = "redis")
  EmailVerificationStore redisSignupVerificationStore(
      StringRedisTemplate redis, Clock clock, EmailVerificationProperties properties) {
    return new RedisEmailVerificationStore(
        redis, clock, SIGNUP, properties.resendCooldown(), properties.hourlyLimit());
  }

  @Bean(PASSWORD_RESET)
  @ConditionalOnProperty(prefix = "app.verification-store", name = "type", havingValue = "redis")
  EmailVerificationStore redisPasswordResetStore(
      StringRedisTemplate redis, Clock clock, PasswordResetProperties properties) {
    return new RedisEmailVerificationStore(
        redis, clock, PASSWORD_RESET, properties.resendCooldown(), properties.hourlyLimit());
  }
}
