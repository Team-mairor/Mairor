package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.users.support.EmailVerificationStore.ConfirmOutcome;
import com.mairor.backend.users.support.EmailVerificationStore.SendPermit;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

/**
 * {@link EmailVerificationStore} 구현이 지켜야 하는 동작. 구현체마다 이 클래스를 상속해 {@link #create}만 채운다. Redis 구현을
 * 추가할 때도 같은 테스트를 통과해야 교체가 끝난 것이다. 특히 동시성 테스트는 "조회 후 쓰기" 경쟁이 없는지 확인한다.
 */
abstract class EmailVerificationStoreContract {

  private static final Instant T0 = Instant.parse("2026-10-27T00:00:00Z");
  private static final String EMAIL = "member@example.com";
  private static final int MAX_ATTEMPTS = 5;

  /** 재발송 간격 {@code cooldown}, 시간당 발송 {@code hourlyLimit}인 새 저장소 (이전 테스트의 상태가 없어야 한다). */
  protected abstract EmailVerificationStore create(Duration cooldown, int hourlyLimit);

  private EmailVerificationStore store() {
    return create(Duration.ofSeconds(60), 5);
  }

  // ---- 발송 예약 ----

  @Test
  void firstSendIsAllowed() {
    SendPermit permit = store().reserveSend(EMAIL, T0);

    assertThat(permit.isAllowed()).isTrue();
    assertThat(permit.retryAfterSeconds()).isZero();
  }

  @Test
  void secondSendWithinTheCooldownIsBlockedWithTheRemainingTime() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);

    SendPermit permit = store.reserveSend(EMAIL, T0.plusSeconds(20));

    assertThat(permit.status()).isEqualTo(SendPermit.Status.COOLDOWN);
    assertThat(permit.retryAfterSeconds()).isEqualTo(40);
  }

  @Test
  void cooldownRetryAfterIsRoundedUpAndNeverZero() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);

    assertThat(store.reserveSend(EMAIL, T0.plusMillis(200)).retryAfterSeconds()).isEqualTo(60);
    assertThat(store.reserveSend(EMAIL, T0.plusMillis(59_500)).retryAfterSeconds()).isEqualTo(1);
  }

  @Test
  void sendIsAllowedAgainOnceTheCooldownHasPassed() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);

    assertThat(store.reserveSend(EMAIL, T0.plusMillis(59_999)).isAllowed()).isFalse();
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(60)).isAllowed()).isTrue();
  }

  @Test
  void blockedAttemptsAreNotRecorded() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);
    for (int i = 1; i < 60; i++) {
      assertThat(store.reserveSend(EMAIL, T0.plusSeconds(i)).isAllowed()).isFalse();
    }

    // 막힌 시도가 쿨다운을 늘리지 않는다: 첫 발송으로부터 60초 뒤에 풀린다
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(60)).isAllowed()).isTrue();
  }

  @Test
  void hourlyLimitBlocksUntilTheOldestSendLeavesTheWindow() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 3);
    for (int i = 0; i < 3; i++) {
      assertThat(store.reserveSend(EMAIL, T0.plusSeconds(60L * i)).isAllowed()).isTrue();
    }

    SendPermit permit = store.reserveSend(EMAIL, T0.plusSeconds(180));

    assertThat(permit.status()).isEqualTo(SendPermit.Status.HOURLY_LIMIT);
    assertThat(permit.retryAfterSeconds()).isEqualTo(3600 - 180);
    // 가장 오래된 발송(T0)이 1시간 창을 벗어나면 다시 허용된다
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(3599)).isAllowed()).isFalse();
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(3600)).isAllowed()).isTrue();
  }

  @Test
  void whenBothCooldownAndHourlyLimitApply_theHourlyLimitIsReported() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 1);
    store.reserveSend(EMAIL, T0);

    // 쿨다운도 걸려 있지만 시간당 한도가 더 오래 기다려야 하므로 그것을 알려 준다
    SendPermit permit = store.reserveSend(EMAIL, T0.plusSeconds(10));

    assertThat(permit.status()).isEqualTo(SendPermit.Status.HOURLY_LIMIT);
    assertThat(permit.retryAfterSeconds()).isEqualTo(3590);
  }

  @Test
  void sendLimitsAreTrackedPerEmail() {
    EmailVerificationStore store = store();

    assertThat(store.reserveSend("a@example.com", T0).isAllowed()).isTrue();
    assertThat(store.reserveSend("a@example.com", T0).isAllowed()).isFalse();
    assertThat(store.reserveSend("b@example.com", T0).isAllowed()).isTrue();
  }

  @Test
  void cancelSendRestoresTheCooldownAndTheHourlyCount() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 1);
    store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash", T0.plusSeconds(600));

    store.cancelSend(EMAIL);

    // 쿨다운과 시간당 횟수에서 빠져 같은 시각에 바로 다시 보낼 수 있다
    assertThat(store.reserveSend(EMAIL, T0).isAllowed()).isTrue();
  }

  @Test
  void cancelSendDiscardsTheCode() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash", T0.plusSeconds(600));

    store.cancelSend(EMAIL);

    assertThat(store.confirmCode(EMAIL, "hash", T0.plusSeconds(1), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void cancelSendOnlyRemovesTheLatestReservation() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 2);
    store.reserveSend(EMAIL, T0);
    store.reserveSend(EMAIL, T0.plusSeconds(60));

    store.cancelSend(EMAIL);

    // 첫 발송은 남아 있어서 한도(2) 중 1을 쓴 상태 → 쿨다운이 지난 뒤 한 번 더 허용, 그다음은 막힘
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(60)).isAllowed()).isTrue();
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(120)).status())
        .isEqualTo(SendPermit.Status.HOURLY_LIMIT);
  }

  @Test
  void cancelSendWithoutAReservationDoesNothing() {
    EmailVerificationStore store = store();

    store.cancelSend(EMAIL);

    assertThat(store.reserveSend(EMAIL, T0).isAllowed()).isTrue();
  }

  // ---- 인증번호 확인 ----

  @Test
  void correctCodeIsAcceptedOnceOnly() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(10), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(11), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void wrongCodeIsAMismatchAndTheCodeStaysUsable() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    assertThat(store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void afterTheAllowedWrongAttempts_evenTheCorrectCodeIsRefused() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));
    for (int i = 0; i < MAX_ATTEMPTS; i++) {
      assertThat(store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS))
          .as("틀린 시도 %d", i + 1)
          .isEqualTo(ConfirmOutcome.MISMATCH);
    }

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.ATTEMPTS_EXCEEDED);
    assertThat(store.confirmCode(EMAIL, "wrong", T0.plusSeconds(3), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.ATTEMPTS_EXCEEDED);
  }

  @Test
  void correctCodeAfterFewerWrongAttemptsStillWorks() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));
    for (int i = 0; i < MAX_ATTEMPTS - 1; i++) {
      store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS);
    }

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void codeIsExpiredAtExactlyItsExpiryTime() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(600), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void codeIsStillValidJustBeforeItsExpiryTime() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusMillis(599_999), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void neverSentCodeIsReportedLikeAnExpiredOne() {
    assertThat(store().confirmCode(EMAIL, "hash-1", T0, MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void resendReplacesTheOldCodeAndResetsTheAttempts() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));
    for (int i = 0; i < MAX_ATTEMPTS; i++) {
      store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS);
    }

    store.saveCode(EMAIL, "hash-2", T0.plusSeconds(1200));

    // 이전 코드는 무효, 새 코드는 시도 횟수가 처음부터
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(61), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode(EMAIL, "hash-2", T0.plusSeconds(62), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void codesAreTrackedPerEmail() {
    EmailVerificationStore store = store();
    store.saveCode("a@example.com", "hash-a", T0.plusSeconds(600));
    store.saveCode("b@example.com", "hash-b", T0.plusSeconds(600));

    assertThat(store.confirmCode("a@example.com", "hash-b", T0, MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode("b@example.com", "hash-b", T0, MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void savingACodeDoesNotResetTheSendHistory() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(1)).status())
        .isEqualTo(SendPermit.Status.COOLDOWN);
  }

  @Test
  void confirmingACodeDoesNotResetTheSendHistory() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));
    store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(5), MAX_ATTEMPTS);

    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(6)).status())
        .isEqualTo(SendPermit.Status.COOLDOWN);
  }

  // ---- 토큰 ----

  @Test
  void tokenIsValidForItsEmailBeforeExpiry() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(1800));

    assertThat(store.hasValidToken("token-hash", EMAIL, T0.plusSeconds(10))).isTrue();
  }

  @Test
  void checkingATokenDoesNotConsumeIt() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(1800));

    assertThat(store.hasValidToken("token-hash", EMAIL, T0)).isTrue();
    assertThat(store.hasValidToken("token-hash", EMAIL, T0.plusSeconds(1))).isTrue();
  }

  @Test
  void tokenIsNotValidForAnotherEmail() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(1800));

    assertThat(store.hasValidToken("token-hash", "other@example.com", T0)).isFalse();
  }

  @Test
  void unknownTokenIsNotValid() {
    assertThat(store().hasValidToken("nope", EMAIL, T0)).isFalse();
  }

  @Test
  void tokenExpiresAtExactlyItsExpiryTime() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(1800));

    assertThat(store.hasValidToken("token-hash", EMAIL, T0.plusMillis(1_799_999))).isTrue();
    assertThat(store.hasValidToken("token-hash", EMAIL, T0.plusSeconds(1800))).isFalse();
  }

  @Test
  void deletedTokenIsNoLongerValid() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(1800));

    store.deleteToken("token-hash");

    assertThat(store.hasValidToken("token-hash", EMAIL, T0)).isFalse();
  }

  @Test
  void deletingAnUnknownTokenDoesNothing() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(1800));

    store.deleteToken("other");

    assertThat(store.hasValidToken("token-hash", EMAIL, T0)).isTrue();
  }

  // ---- 동시성 ----

  @Test
  void concurrentWrongCodesCountEveryAttempt() throws Exception {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    List<ConfirmOutcome> outcomes =
        runConcurrently(64, () -> store.confirmCode(EMAIL, "wrong", T0, MAX_ATTEMPTS));

    // 시도가 하나도 유실되지 않으면 정확히 MAX_ATTEMPTS 번만 틀림으로 판정되고 나머지는 시도 초과
    assertThat(outcomes).filteredOn(o -> o == ConfirmOutcome.MISMATCH).hasSize(MAX_ATTEMPTS);
    assertThat(outcomes)
        .filteredOn(o -> o == ConfirmOutcome.ATTEMPTS_EXCEEDED)
        .hasSize(64 - MAX_ATTEMPTS);
  }

  @Test
  void concurrentCorrectCodesSucceedExactlyOnce() throws Exception {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600));

    List<ConfirmOutcome> outcomes =
        runConcurrently(64, () -> store.confirmCode(EMAIL, "hash-1", T0, MAX_ATTEMPTS));

    assertThat(outcomes).filteredOn(o -> o == ConfirmOutcome.OK).hasSize(1);
    assertThat(outcomes).filteredOn(o -> o == ConfirmOutcome.EXPIRED_OR_MISSING).hasSize(63);
  }

  @Test
  void concurrentSendReservationsAllowExactlyOne() throws Exception {
    EmailVerificationStore store = store();

    List<SendPermit> permits = runConcurrently(64, () -> store.reserveSend(EMAIL, T0));

    assertThat(permits).filteredOn(SendPermit::isAllowed).hasSize(1);
  }

  @Test
  void concurrentSendReservationsNeverExceedTheHourlyLimit() throws Exception {
    // 쿨다운 없이 시간당 한도만 본다
    EmailVerificationStore store = create(Duration.ZERO, 5);

    List<SendPermit> permits = runConcurrently(64, () -> store.reserveSend(EMAIL, T0));

    assertThat(permits).filteredOn(SendPermit::isAllowed).hasSize(5);
  }

  private static <T> List<T> runConcurrently(int threads, Callable<T> task) throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch ready = new CountDownLatch(threads);
    CountDownLatch go = new CountDownLatch(1);
    try {
      List<Future<T>> futures = new ArrayList<>();
      for (int i = 0; i < threads; i++) {
        futures.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  return task.call();
                }));
      }
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();
      List<T> results = new ArrayList<>();
      for (Future<T> future : futures) {
        results.add(future.get(30, TimeUnit.SECONDS));
      }
      return results;
    } finally {
      pool.shutdownNow();
    }
  }
}
