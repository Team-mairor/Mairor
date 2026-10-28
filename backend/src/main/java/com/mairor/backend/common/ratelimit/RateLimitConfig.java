package com.mairor.backend.common.ratelimit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 용도별 요청 제한 빈. 모두 인메모리 구현이라 서버 1대에서만 정확하다. */
@Configuration
public class RateLimitConfig {

  private static final Logger log = LoggerFactory.getLogger(RateLimitConfig.class);

  /** 이메일 중복 확인(API-USERS-011). 키는 클라이언트 IP. */
  @Bean
  RateLimiter emailAvailabilityRateLimiter(RateLimitProperties properties) {
    log.warn("요청 제한을 인메모리로 처리합니다. 서버 1대에서만 정확하고 재시작하면 카운트가 초기화됩니다.");
    RateLimitProperties.Rule rule = properties.emailAvailability();
    return new InMemoryRateLimiter(rule.limit(), rule.window());
  }

  /**
   * 가입 이메일 인증번호 발송. 키는 클라이언트 IP. 이메일마다 쿨다운·시간당 횟수 제한이 따로 있지만, 한 곳에서 여러 이메일로 보내 메일을 쏟아내는 것은 이쪽에서
   * 막는다.
   */
  @Bean
  RateLimiter emailVerificationRateLimiter(RateLimitProperties properties) {
    RateLimitProperties.Rule rule = properties.emailVerification();
    return new InMemoryRateLimiter(rule.limit(), rule.window());
  }
}
