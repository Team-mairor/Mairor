package com.mairor.backend.users.support;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * 인증 임시 상태 저장소 구현을 고른다 ({@code app.verification-store.type}). 지금은 {@code memory}뿐이다. Redis 를 도입하면
 * {@code redis} 구현을 여기에 더하고 기본값을 바꾼다.
 */
@Configuration
public class EmailVerificationStoreConfig {

  private static final Logger log = LoggerFactory.getLogger(EmailVerificationStoreConfig.class);

  @Bean
  @ConditionalOnProperty(
      prefix = "app.verification-store",
      name = "type",
      havingValue = "memory",
      matchIfMissing = true)
  EmailVerificationStore inMemoryEmailVerificationStore(EmailVerificationProperties properties) {
    log.warn("이메일 인증 임시 상태를 인메모리에 둡니다. 서버 1대에서만 정확하고 재시작하면 진행 중인 인증이 사라집니다.");
    return new InMemoryEmailVerificationStore(
        properties.resendCooldown(), properties.hourlyLimit());
  }
}
