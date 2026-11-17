package com.mairor.backend.common.ratelimit;

import com.mairor.backend.testsupport.RedisTestServer;
import java.time.Duration;
import java.util.UUID;

/** Redis 구현이 인메모리와 같은 계약을 지키는지 실제 Redis 로 확인한다. 테스트마다 키 이름공간을 새로 써서 카운트가 섞이지 않는다. */
class RedisRateLimiterTest extends RateLimiterContract {

  @Override
  protected RateLimiter create(int limit, Duration window) {
    return new RedisRateLimiter(
        RedisTestServer.template(), "test-" + UUID.randomUUID(), limit, window);
  }
}
