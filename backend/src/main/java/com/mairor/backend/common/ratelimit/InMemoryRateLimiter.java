package com.mairor.backend.common.ratelimit;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.time.Instant;

/**
 * 인메모리(Caffeine) 고정 시간 창 요청 제한. 키마다 첫 시도 시각부터 {@code window} 동안 최대 {@code limit}번까지 허용하고, 키 단위
 * {@code compute}로 동시 요청이 한도를 넘지 못하게 한다.
 *
 * <p>한계: 창 경계에서 짧게 한도의 두 배가 지나갈 수 있고, 서버마다 따로 세며 재시작하면 초기화된다.
 */
public class InMemoryRateLimiter implements RateLimiter {

  /** 키가 이 수를 넘으면 오래된 것부터 잊는다 (메모리 상한). */
  private static final long MAX_KEYS = 100_000;

  private record Window(Instant start, int count) {}

  private final int limit;
  private final Duration window;
  private final Cache<String, Window> counters;

  public InMemoryRateLimiter(int limit, Duration window) {
    if (limit < 1) {
      throw new IllegalArgumentException("limit 은 1 이상이어야 합니다: " + limit);
    }
    if (window.isZero() || window.isNegative()) {
      throw new IllegalArgumentException("window 는 0보다 길어야 합니다: " + window);
    }
    this.limit = limit;
    this.window = window;
    this.counters = Caffeine.newBuilder().expireAfterWrite(window).maximumSize(MAX_KEYS).build();
  }

  @Override
  public Decision tryAcquire(String key, Instant now) {
    Decision[] result = new Decision[1];
    counters
        .asMap()
        .compute(
            key,
            (k, current) -> {
              if (current == null || !now.isBefore(current.start().plus(window))) {
                result[0] = Decision.permit();
                return new Window(now, 1);
              }
              if (current.count() < limit) {
                result[0] = Decision.permit();
                return new Window(current.start(), current.count() + 1);
              }
              result[0] = Decision.limited(secondsUntil(current.start().plus(window), now));
              return current;
            });
    return result[0];
  }

  /** 남은 시간을 올림한 초. 항상 1 이상이라 {@code Retry-After: 0}이 나가지 않는다. */
  private static long secondsUntil(Instant end, Instant now) {
    long millis = Duration.between(now, end).toMillis();
    return Math.max(1, (millis + 999) / 1000);
  }
}
