package com.mairor.backend.users.support;

import com.mairor.backend.testsupport.RedisTestServer;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;

/**
 * Redis 구현이 인메모리와 같은 계약을 지키는지 실제 Redis 로 확인한다. 테스트마다 키 이름공간을 새로 쓴다. 키의 만료 시간(TTL)은 시계로 계산하므로 계약이 쓰는
 * 시각에 맞춘 시계를 준다.
 */
class RedisEmailVerificationStoreTest extends EmailVerificationStoreContract {

  @Override
  protected EmailVerificationStore create(Duration cooldown, int hourlyLimit) {
    return new RedisEmailVerificationStore(
        RedisTestServer.template(),
        Clock.fixed(Instant.parse("2026-10-27T00:00:00Z"), ZoneOffset.UTC),
        "test-" + UUID.randomUUID(),
        cooldown,
        hourlyLimit);
  }
}
