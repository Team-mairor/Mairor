package com.mairor.backend.common.ratelimit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

/**
 * {@link RateLimiter} 구현이 지켜야 하는 동작. 구현체마다 이 클래스를 상속해 {@link #create}만 채운다. Redis 구현을 추가할 때도 같은
 * 테스트를 통과해야 교체가 끝난 것이다.
 */
abstract class RateLimiterContract {

  private static final Instant T0 = Instant.parse("2026-10-27T00:00:00Z");

  /** 한도 {@code limit}, 시간 창 {@code window}인 새 제한기 (이전 테스트의 카운트가 없어야 한다). */
  protected abstract RateLimiter create(int limit, Duration window);

  @Test
  void allowsUpToTheLimitThenBlocks() {
    RateLimiter limiter = create(3, Duration.ofMinutes(1));

    for (int i = 0; i < 3; i++) {
      assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(i)).allowed())
          .as("시도 %d", i + 1)
          .isTrue();
    }
    RateLimiter.Decision blocked = limiter.tryAcquire("ip-1", T0.plusSeconds(3));

    assertThat(blocked.allowed()).isFalse();
  }

  @Test
  void allowedDecisionHasNoRetryAfter() {
    RateLimiter limiter = create(1, Duration.ofMinutes(1));

    assertThat(limiter.tryAcquire("ip-1", T0).retryAfterSeconds()).isZero();
  }

  @Test
  void blockedDecisionTellsHowLongToWaitRoundedUp() {
    RateLimiter limiter = create(1, Duration.ofSeconds(60));
    limiter.tryAcquire("ip-1", T0);

    // 시간 창 끝까지 59.2초 남음 → 올림해서 60
    assertThat(limiter.tryAcquire("ip-1", T0.plusMillis(800)).retryAfterSeconds()).isEqualTo(60);
    // 정확히 30초 남음
    assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(30)).retryAfterSeconds()).isEqualTo(30);
    // 0.5초 남아도 0 이 아니라 1
    assertThat(limiter.tryAcquire("ip-1", T0.plusMillis(59_500)).retryAfterSeconds()).isEqualTo(1);
  }

  @Test
  void allowsAgainWhenTheWindowHasPassed() {
    RateLimiter limiter = create(2, Duration.ofMinutes(1));
    limiter.tryAcquire("ip-1", T0);
    limiter.tryAcquire("ip-1", T0.plusSeconds(1));
    assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(2)).allowed()).isFalse();

    // 첫 시도로부터 정확히 1분이 지나면 새 시간 창이다
    assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(60)).allowed()).isTrue();
    assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(61)).allowed()).isTrue();
    assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(62)).allowed()).isFalse();
  }

  @Test
  void stillBlockedJustBeforeTheWindowEnds() {
    RateLimiter limiter = create(1, Duration.ofMinutes(1));
    limiter.tryAcquire("ip-1", T0);

    assertThat(limiter.tryAcquire("ip-1", T0.plusMillis(59_999)).allowed()).isFalse();
  }

  @Test
  void blockedAttemptsDoNotExtendTheWindow() {
    RateLimiter limiter = create(1, Duration.ofMinutes(1));
    limiter.tryAcquire("ip-1", T0);
    for (int i = 1; i < 60; i++) {
      assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(i)).allowed()).isFalse();
    }

    // 막힌 시도를 아무리 해도 첫 시도 기준으로 1분이 지나면 풀린다
    assertThat(limiter.tryAcquire("ip-1", T0.plusSeconds(60)).allowed()).isTrue();
  }

  @Test
  void keysAreIndependent() {
    RateLimiter limiter = create(1, Duration.ofMinutes(1));

    assertThat(limiter.tryAcquire("ip-1", T0).allowed()).isTrue();
    assertThat(limiter.tryAcquire("ip-1", T0).allowed()).isFalse();
    assertThat(limiter.tryAcquire("ip-2", T0).allowed()).isTrue();
  }

  @Test
  void concurrentRequestsNeverExceedTheLimit() throws Exception {
    int limit = 10;
    int threads = 64;
    RateLimiter limiter = create(limit, Duration.ofMinutes(1));
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch ready = new CountDownLatch(threads);
    CountDownLatch go = new CountDownLatch(1);
    try {
      List<Future<Boolean>> results = new ArrayList<>();
      for (int i = 0; i < threads; i++) {
        results.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  return limiter.tryAcquire("shared", T0).allowed();
                }));
      }
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();

      int allowed = 0;
      for (Future<Boolean> result : results) {
        if (result.get(30, TimeUnit.SECONDS)) {
          allowed++;
        }
      }
      assertThat(allowed).isEqualTo(limit);
    } finally {
      pool.shutdownNow();
    }
  }
}
