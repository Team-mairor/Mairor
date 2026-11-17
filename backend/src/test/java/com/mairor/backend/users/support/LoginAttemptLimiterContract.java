package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.users.support.LoginAttemptLimiter.Allowed;
import com.mairor.backend.users.support.LoginAttemptLimiter.Locked;
import com.mairor.backend.users.support.LoginAttemptLimiter.Pending;
import com.mairor.backend.users.support.LoginAttemptLimiter.Result;
import com.mairor.backend.users.support.LoginAttemptLimiter.Saturated;
import com.mairor.backend.users.support.LoginAttemptLimiter.Ticket;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

/**
 * {@link LoginAttemptLimiter} 구현이 지켜야 하는 동작. 구현체마다 이 클래스를 상속해 {@link #create} 만 채운다. Redis 구현을 추가할
 * 때도 같은 테스트를 통과해야 교체가 끝난 것이다.
 */
abstract class LoginAttemptLimiterContract {

  protected static final Instant T0 = Instant.parse("2026-10-29T00:00:00Z");

  /** 이전 테스트의 상태가 없는 새 제한기. */
  protected abstract LoginAttemptLimiter create(
      int maxFailures, Duration lockDuration, Duration attemptTtl, int maxEntries);

  private LoginAttemptLimiter create(int maxFailures) {
    return create(maxFailures, Duration.ofSeconds(30), Duration.ofMinutes(15), 1_000);
  }

  protected static Ticket acquire(LoginAttemptLimiter limiter, String email, Instant now) {
    Result result = limiter.tryAcquire(email, now);
    assertThat(result).as("%s 의 시도", email).isInstanceOf(Allowed.class);
    return ((Allowed) result).ticket();
  }

  /** 시도를 시작해 바로 실패로 끝낸다. */
  private static void failOnce(LoginAttemptLimiter limiter, String email, Instant now) {
    limiter.fail(acquire(limiter, email, now), now);
  }

  // ---- 잠금 ----

  @Test
  void locksAfterTheThresholdOfConfirmedFailures() {
    LoginAttemptLimiter limiter = create(3);

    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0.plusSeconds(1));
    // 세 번째 시도는 아직 허용된다
    Ticket third = acquire(limiter, "a@x.com", T0.plusSeconds(2));
    limiter.fail(third, T0.plusSeconds(2));

    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(3))).isInstanceOf(Locked.class);
  }

  @Test
  void lockedDecisionTellsHowLongToWaitRoundedUp() {
    LoginAttemptLimiter limiter = create(1);
    failOnce(limiter, "a@x.com", T0);

    // 잠금 끝(T0+30s)까지 29.2초 → 올림해서 30
    assertThat(limiter.tryAcquire("a@x.com", T0.plusMillis(800))).isEqualTo(new Locked(30));
    // 0.5초 남아도 0 이 아니라 1
    assertThat(limiter.tryAcquire("a@x.com", T0.plusMillis(29_500))).isEqualTo(new Locked(1));
  }

  @Test
  void attemptsWhileLockedDoNotExtendTheLock() {
    LoginAttemptLimiter limiter = create(1);
    failOnce(limiter, "a@x.com", T0);
    for (int i = 1; i < 30; i++) {
      assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(i))).isInstanceOf(Locked.class);
    }

    // 잠금 중 아무리 시도해도 처음 잠긴 시각 기준으로 30초 뒤에 풀린다
    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(30))).isInstanceOf(Allowed.class);
  }

  @Test
  void countsFromZeroAgainAfterTheLockEnds() {
    LoginAttemptLimiter limiter = create(3);
    for (int i = 0; i < 3; i++) {
      failOnce(limiter, "a@x.com", T0);
    }
    Instant later = T0.plusSeconds(31);

    failOnce(limiter, "a@x.com", later);
    failOnce(limiter, "a@x.com", later);

    // 잠금이 끝난 뒤에는 다시 세 번까지 허용된다 (이전 실패가 남아 있지 않다)
    assertThat(limiter.tryAcquire("a@x.com", later)).isInstanceOf(Allowed.class);
  }

  @Test
  void emailsAreIndependent() {
    LoginAttemptLimiter limiter = create(1);
    failOnce(limiter, "a@x.com", T0);

    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Locked.class);
    assertThat(limiter.tryAcquire("b@x.com", T0)).isInstanceOf(Allowed.class);
  }

  // ---- 성공·환불·종료 ----

  @Test
  void successClearsConfirmedFailures() {
    LoginAttemptLimiter limiter = create(3);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    limiter.succeed(acquire(limiter, "a@x.com", T0));

    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);

    // 성공으로 초기화됐으므로 실패 2번 뒤에도 잠기지 않았다
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
  }

  @Test
  void refundNeverCountsAsAFailure() {
    LoginAttemptLimiter limiter = create(3);

    for (int i = 0; i < 20; i++) {
      limiter.refund(acquire(limiter, "a@x.com", T0));
    }

    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
  }

  @Test
  void aTicketIsClosedOnlyOnce() {
    LoginAttemptLimiter limiter = create(2);
    Ticket ticket = acquire(limiter, "a@x.com", T0);
    acquire(limiter, "a@x.com", T0); // 다른 시도가 열려 있어 상태가 유지된다

    limiter.refund(ticket);
    limiter.refund(ticket);

    // 자리는 한 번만 반환됐으므로 하나 더 받을 수 있고 그 다음은 Pending.
    // 이중 반환이면 자리가 하나 더 비어 둘 다 허용된다
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Pending.class);
  }

  @Test
  void aClosedTicketCannotBeClosedAgainWithAnotherOutcome() {
    LoginAttemptLimiter limiter = create(3);
    failOnce(limiter, "a@x.com", T0);
    Ticket ticket = acquire(limiter, "a@x.com", T0);
    limiter.fail(ticket, T0);

    // 이미 실패로 종료된 ticket 의 성공 호출은 무시된다 → 확정 실패 2 가 지워지지 않는다
    limiter.succeed(ticket);
    failOnce(limiter, "a@x.com", T0);

    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Locked.class);
  }

  // ---- 초기화 (비밀번호 재설정) ----

  @Test
  void resetUnlocksALockedEmail() {
    LoginAttemptLimiter limiter = create(1);
    failOnce(limiter, "a@x.com", T0);
    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(1))).isInstanceOf(Locked.class);

    limiter.reset("a@x.com");

    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(1))).isInstanceOf(Allowed.class);
  }

  @Test
  void resetClearsConfirmedFailures() {
    LoginAttemptLimiter limiter = create(3);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);

    limiter.reset("a@x.com");

    // 실패 2 가 남아 있었다면 두 번째 실패에서 잠겼을 것이다
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
  }

  @Test
  void resetAfterTheLockStartsCountingFromZeroAgain() {
    LoginAttemptLimiter limiter = create(2);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    limiter.reset("a@x.com");

    failOnce(limiter, "a@x.com", T0.plusSeconds(1));

    // 초기화 뒤 첫 실패일 뿐이라 아직 잠기지 않는다
    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(1))).isInstanceOf(Allowed.class);
  }

  @Test
  void resetOnlyAffectsTheGivenEmail() {
    LoginAttemptLimiter limiter = create(1);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "b@x.com", T0);

    limiter.reset("a@x.com");

    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
    assertThat(limiter.tryAcquire("b@x.com", T0)).isInstanceOf(Locked.class);
  }

  @Test
  void resetOfAnEmailWithoutStateDoesNothing() {
    LoginAttemptLimiter limiter = create(2);

    limiter.reset("unknown@x.com");

    failOnce(limiter, "unknown@x.com", T0);
    assertThat(limiter.tryAcquire("unknown@x.com", T0)).isInstanceOf(Allowed.class);
  }

  @Test
  void resetKeepsAttemptsThatAreStillInFlightCounted() {
    LoginAttemptLimiter limiter = create(3);
    Ticket inFlight = acquire(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);

    limiter.reset("a@x.com");

    // 확정 실패는 지워졌지만 진행 중인 시도는 그대로 자리를 차지한다: 둘 더 허용, 그 뒤는 Pending
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Pending.class);
    limiter.refund(inFlight);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
  }

  @Test
  void aTicketOpenedBeforeTheResetStillClosesNormally() {
    LoginAttemptLimiter limiter = create(2);
    Ticket before = acquire(limiter, "a@x.com", T0);

    limiter.reset("a@x.com");
    limiter.fail(before, T0);

    // 초기화 전에 시작한 시도의 실패는 초기화 뒤의 첫 실패로 센다: 아직 잠기지 않았고(한 건), 한 번 더 실패하면 잠긴다
    Ticket next = acquire(limiter, "a@x.com", T0);
    limiter.fail(next, T0);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Locked.class);
  }

  @Test
  void resetFreesTheSlotOfALockedEmailWhenTheStoreIsFull() {
    LoginAttemptLimiter limiter = create(1, Duration.ofSeconds(30), Duration.ofMinutes(15), 2);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "b@x.com", T0.plusSeconds(1));
    assertThat(limiter.tryAcquire("c@x.com", T0.plusSeconds(2))).isInstanceOf(Saturated.class);

    limiter.reset("a@x.com");

    assertThat(limiter.tryAcquire("c@x.com", T0.plusSeconds(2))).isInstanceOf(Allowed.class);
  }

  @Test
  void slotsAreNeverExceededWhileResettingConcurrently() throws Exception {
    int maxFailures = 3;
    int threads = 16;
    int rounds = 300;
    LoginAttemptLimiter limiter = create(maxFailures);
    AtomicInteger inside = new AtomicInteger();
    AtomicInteger maxInside = new AtomicInteger();
    ExecutorService pool = Executors.newFixedThreadPool(threads + 1);
    CountDownLatch ready = new CountDownLatch(threads + 1);
    CountDownLatch go = new CountDownLatch(1);
    try {
      List<Future<?>> futures = new ArrayList<>();
      for (int t = 0; t < threads; t++) {
        futures.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  for (int r = 0; r < rounds; r++) {
                    if (limiter.tryAcquire("shared@x.com", T0) instanceof Allowed allowed) {
                      maxInside.accumulateAndGet(inside.incrementAndGet(), Math::max);
                      Thread.onSpinWait();
                      inside.decrementAndGet();
                      limiter.fail(allowed.ticket(), T0);
                    }
                  }
                  return null;
                }));
      }
      futures.add(
          pool.submit(
              () -> {
                ready.countDown();
                go.await();
                for (int r = 0; r < rounds * 4; r++) {
                  limiter.reset("shared@x.com");
                }
                return null;
              }));
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();
      for (Future<?> future : futures) {
        future.get(60, TimeUnit.SECONDS);
      }
    } finally {
      pool.shutdownNow();
    }

    assertThat(maxInside.get()).isLessThanOrEqualTo(maxFailures);
    limiter.reset("shared@x.com");
    // 끝난 뒤에는 자리가 새지 않았고 잠금도 남지 않는다: 다시 세 번 모두 허용된다
    for (int i = 0; i < maxFailures; i++) {
      assertThat(limiter.tryAcquire("shared@x.com", T0)).isInstanceOf(Allowed.class);
    }
  }

  // ---- 임계치에 닿는 요청 ----

  @Test
  void theThresholdRequestFailingLocks() {
    LoginAttemptLimiter limiter = create(3);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    Ticket third = acquire(limiter, "a@x.com", T0);

    limiter.fail(third, T0);

    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Locked.class);
  }

  @Test
  void theThresholdRequestSucceedingResets() {
    LoginAttemptLimiter limiter = create(3);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    Ticket third = acquire(limiter, "a@x.com", T0);

    limiter.succeed(third);

    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
  }

  @Test
  void theThresholdRequestRefundedRestoresTheCount() {
    LoginAttemptLimiter limiter = create(3);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    Ticket third = acquire(limiter, "a@x.com", T0);

    limiter.refund(third);

    // 확정 실패는 그대로 2 → 다음 시도가 다시 세 번째가 되고, 그 실패로 잠긴다
    failOnce(limiter, "a@x.com", T0);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Locked.class);
  }

  @Test
  void aRefundMadeWhileOthersAreInFlightIsNotLost() {
    LoginAttemptLimiter limiter = create(3);
    // A·B·C 가 자리를 모두 잡는다
    Ticket a = acquire(limiter, "a@x.com", T0);
    Ticket b = acquire(limiter, "a@x.com", T0);
    Ticket c = acquire(limiter, "a@x.com", T0);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Pending.class);

    limiter.refund(a); // 내부 오류
    limiter.refund(c); // BCrypt 상한 거절
    limiter.fail(b, T0); // 확정 실패는 이 한 건뿐

    // 확정 실패가 1 이므로 한 번 더 실패해도 2. 아직 잠기지 않았다
    failOnce(limiter, "a@x.com", T0);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
  }

  // ---- 동시성 ----

  @Test
  void concurrentAttemptsNeverExceedTheSlots() throws Exception {
    int maxFailures = 3;
    int threads = 64;
    LoginAttemptLimiter limiter = create(maxFailures);
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch ready = new CountDownLatch(threads);
    CountDownLatch go = new CountDownLatch(1);
    try {
      List<Future<Result>> results = new ArrayList<>();
      for (int i = 0; i < threads; i++) {
        results.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  return limiter.tryAcquire("shared@x.com", T0);
                }));
      }
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();

      int allowed = 0;
      int pending = 0;
      for (Future<Result> future : results) {
        Result result = future.get(30, TimeUnit.SECONDS);
        if (result instanceof Allowed) {
          allowed++;
        } else if (result instanceof Pending) {
          pending++;
        }
      }
      assertThat(allowed).isEqualTo(maxFailures);
      assertThat(pending).isEqualTo(threads - maxFailures);
    } finally {
      pool.shutdownNow();
    }
  }

  @Test
  void slotsAreNeverExceededWhileAttemptsAreRefundedConcurrently() throws Exception {
    int maxFailures = 3;
    int threads = 32;
    int rounds = 300;
    LoginAttemptLimiter limiter = create(maxFailures);
    AtomicInteger inside = new AtomicInteger();
    AtomicInteger maxInside = new AtomicInteger();
    AtomicInteger unexpected = new AtomicInteger();
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch ready = new CountDownLatch(threads);
    CountDownLatch go = new CountDownLatch(1);
    try {
      List<Future<?>> futures = new ArrayList<>();
      for (int t = 0; t < threads; t++) {
        futures.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  for (int r = 0; r < rounds; r++) {
                    Result result = limiter.tryAcquire("shared@x.com", T0);
                    if (result instanceof Allowed allowed) {
                      maxInside.accumulateAndGet(inside.incrementAndGet(), Math::max);
                      Thread.onSpinWait();
                      inside.decrementAndGet();
                      limiter.refund(allowed.ticket());
                    } else if (!(result instanceof Pending)) {
                      unexpected.incrementAndGet();
                    }
                  }
                  return null;
                }));
      }
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();
      for (Future<?> future : futures) {
        future.get(60, TimeUnit.SECONDS);
      }
    } finally {
      pool.shutdownNow();
    }

    assertThat(maxInside.get()).isLessThanOrEqualTo(maxFailures);
    assertThat(unexpected.get()).as("환불만 했으므로 잠기거나 포화되면 안 된다").isZero();
    // 자리가 새지 않았다: 다시 세 번 모두 허용된다
    for (int i = 0; i < maxFailures; i++) {
      assertThat(limiter.tryAcquire("shared@x.com", T0)).isInstanceOf(Allowed.class);
    }
  }

  @Test
  void pendingAsksToRetryInOneSecond() {
    LoginAttemptLimiter limiter = create(1);
    acquire(limiter, "a@x.com", T0);

    assertThat(limiter.tryAcquire("a@x.com", T0)).isEqualTo(new Pending(1));
  }

  // ---- 보관·용량 ----

  @Test
  void forgetsFailuresAfterTheAttemptTtl() {
    LoginAttemptLimiter limiter = create(3, Duration.ofSeconds(30), Duration.ofMinutes(15), 1_000);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0);
    Instant later = T0.plus(Duration.ofMinutes(16));

    failOnce(limiter, "a@x.com", later);
    failOnce(limiter, "a@x.com", later);

    // 이전 실패 2 가 남아 있었다면 지금쯤 잠겼을 것이다
    assertThat(limiter.tryAcquire("a@x.com", later)).isInstanceOf(Allowed.class);
  }

  @Test
  void evictsTheOldestIdleStateWhenFull() {
    LoginAttemptLimiter limiter = create(3, Duration.ofSeconds(30), Duration.ofMinutes(15), 3);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "a@x.com", T0.plusSeconds(1));
    failOnce(limiter, "b@x.com", T0.plusSeconds(2));
    failOnce(limiter, "c@x.com", T0.plusSeconds(3));

    // 가득 찬 상태에서 새 이메일이 오면 가장 오래된 a 의 상태가 지워진다
    acquire(limiter, "d@x.com", T0.plusSeconds(4));

    failOnce(limiter, "a@x.com", T0.plusSeconds(5));
    failOnce(limiter, "a@x.com", T0.plusSeconds(6));
    // a 의 이전 실패 2 가 남아 있었다면 지금쯤 잠겼을 것이다
    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(7))).isInstanceOf(Allowed.class);
  }

  @Test
  void refusesNewEmailsWhenOnlyLocksFillTheStore() {
    LoginAttemptLimiter limiter = create(1, Duration.ofSeconds(30), Duration.ofMinutes(15), 2);
    failOnce(limiter, "a@x.com", T0);
    failOnce(limiter, "b@x.com", T0.plusSeconds(1));

    // 새 이메일은 BCrypt 전에 거절한다. 가장 빨리 풀리는 a 의 잠금까지 28초
    assertThat(limiter.tryAcquire("c@x.com", T0.plusSeconds(2))).isEqualTo(new Saturated(28));
    // 이미 상태가 있는 이메일은 정상 동작
    assertThat(limiter.tryAcquire("a@x.com", T0.plusSeconds(2))).isInstanceOf(Locked.class);
    // 잠금이 풀리면 자리가 생겨 새 이메일을 받는다
    assertThat(limiter.tryAcquire("c@x.com", T0.plusSeconds(30))).isInstanceOf(Allowed.class);
  }

  @Test
  void neverEvictsStatesWithAttemptsInFlight() {
    LoginAttemptLimiter limiter = create(3, Duration.ofSeconds(30), Duration.ofMinutes(15), 2);
    Ticket a = acquire(limiter, "a@x.com", T0);
    acquire(limiter, "b@x.com", T0);

    // 두 상태 모두 진행 중이라 지울 수 없다
    assertThat(limiter.tryAcquire("c@x.com", T0)).isEqualTo(new Saturated(1));

    limiter.refund(a);
    assertThat(limiter.tryAcquire("c@x.com", T0)).isInstanceOf(Allowed.class);
  }
}
