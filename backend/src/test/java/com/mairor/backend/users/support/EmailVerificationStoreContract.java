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
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
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
    SendPermit permit = store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash", T0.plusSeconds(600), permit.generation());

    store.cancelSend(EMAIL, permit.generation());

    // 쿨다운과 시간당 횟수에서 빠져 같은 시각에 바로 다시 보낼 수 있다
    assertThat(store.reserveSend(EMAIL, T0).isAllowed()).isTrue();
  }

  @Test
  void cancelSendDiscardsTheCodeOfThatGeneration() {
    EmailVerificationStore store = store();
    SendPermit permit = store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash", T0.plusSeconds(600), permit.generation());

    store.cancelSend(EMAIL, permit.generation());

    assertThat(store.confirmCode(EMAIL, "hash", T0.plusSeconds(1), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void cancelSendOnlyRemovesTheGivenReservation() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 2);
    SendPermit first = store.reserveSend(EMAIL, T0);
    SendPermit second = store.reserveSend(EMAIL, T0.plusSeconds(60));

    store.cancelSend(EMAIL, second.generation());

    // 첫 발송은 남아 있어서 한도(2) 중 1을 쓴 상태 → 쿨다운이 지난 뒤 한 번 더 허용, 그다음은 막힘
    assertThat(first.generation()).isNotEqualTo(second.generation());
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(60)).isAllowed()).isTrue();
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(120)).status())
        .isEqualTo(SendPermit.Status.HOURLY_LIMIT);
  }

  @Test
  void cancelSendWithoutAReservationDoesNothing() {
    EmailVerificationStore store = store();

    store.cancelSend(EMAIL, 12345);

    assertThat(store.reserveSend(EMAIL, T0).isAllowed()).isTrue();
  }

  // ---- 발송 세대 ----

  @Test
  void everyAllowedReservationGetsANewGeneration() {
    EmailVerificationStore store = create(Duration.ZERO, 5);

    long first = store.reserveSend(EMAIL, T0).generation();
    long second = store.reserveSend(EMAIL, T0).generation();
    long other = store.reserveSend("other@example.com", T0).generation();

    assertThat(List.of(first, second, other)).doesNotHaveDuplicates();
  }

  @Test
  void aLateCancelDoesNotDeleteTheCodeSavedByANewerReservation() {
    EmailVerificationStore store = create(Duration.ZERO, 5);
    SendPermit slow = store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-slow", T0.plusSeconds(600), slow.generation());
    // 느린 요청의 메일이 아직 나가지 않은 사이에 같은 이메일로 새 인증번호가 저장된다
    SendPermit newer = store.reserveSend(EMAIL, T0.plusSeconds(1));
    store.saveCode(EMAIL, "hash-new", T0.plusSeconds(601), newer.generation());

    // 느린 요청의 메일 발송이 실패해 취소한다
    store.cancelSend(EMAIL, slow.generation());

    assertThat(store.confirmCode(EMAIL, "hash-new", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void aLateCancelStillGivesBackItsOwnSendRecord() {
    EmailVerificationStore store = create(Duration.ZERO, 2);
    SendPermit slow = store.reserveSend(EMAIL, T0);
    SendPermit newer = store.reserveSend(EMAIL, T0.plusSeconds(1));
    store.saveCode(EMAIL, "hash-new", T0.plusSeconds(601), newer.generation());
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(2)).status())
        .isEqualTo(SendPermit.Status.HOURLY_LIMIT);

    store.cancelSend(EMAIL, slow.generation());

    // 취소한 예약만큼 시간당 횟수가 돌아와 한 번 더 보낼 수 있다
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(2)).isAllowed()).isTrue();
  }

  @Test
  void aCodeSavedByAnOlderReservationDoesNotReplaceANewerCode() {
    EmailVerificationStore store = create(Duration.ZERO, 5);
    SendPermit old = store.reserveSend(EMAIL, T0);
    SendPermit newer = store.reserveSend(EMAIL, T0.plusSeconds(1));
    store.saveCode(EMAIL, "hash-new", T0.plusSeconds(601), newer.generation());

    // 늦게 도착한 오래된 예약의 저장은 무시된다
    store.saveCode(EMAIL, "hash-old", T0.plusSeconds(600), old.generation());

    assertThat(store.confirmCode(EMAIL, "hash-old", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode(EMAIL, "hash-new", T0.plusSeconds(3), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void cancelAfterTheCodeWasUsedOnlyGivesBackTheSendRecord() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 1);
    SendPermit permit = store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash", T0.plusSeconds(600), permit.generation());
    store.confirmCode(EMAIL, "hash", T0.plusSeconds(1), MAX_ATTEMPTS);

    store.cancelSend(EMAIL, permit.generation());

    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(2)).isAllowed()).isTrue();
  }

  // ---- 인증번호 확인 ----

  @Test
  void correctCodeIsAcceptedOnceOnly() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(10), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(11), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void wrongCodeIsAMismatchAndTheCodeStaysUsable() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

    assertThat(store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void afterTheAllowedWrongAttempts_evenTheCorrectCodeIsRefused() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);
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
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);
    for (int i = 0; i < MAX_ATTEMPTS - 1; i++) {
      store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS);
    }

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void codeIsExpiredAtExactlyItsExpiryTime() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(600), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void codeIsStillValidJustBeforeItsExpiryTime() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

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
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);
    for (int i = 0; i < MAX_ATTEMPTS; i++) {
      store.confirmCode(EMAIL, "wrong", T0.plusSeconds(1), MAX_ATTEMPTS);
    }

    store.saveCode(EMAIL, "hash-2", T0.plusSeconds(1200), 2);

    // 이전 코드는 무효, 새 코드는 시도 횟수가 처음부터
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(61), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode(EMAIL, "hash-2", T0.plusSeconds(62), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void codesAreTrackedPerEmail() {
    EmailVerificationStore store = store();
    store.saveCode("a@example.com", "hash-a", T0.plusSeconds(600), 1);
    store.saveCode("b@example.com", "hash-b", T0.plusSeconds(600), 1);

    assertThat(store.confirmCode("a@example.com", "hash-b", T0, MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode("b@example.com", "hash-b", T0, MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void savingACodeDoesNotResetTheSendHistory() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(1)).status())
        .isEqualTo(SendPermit.Status.COOLDOWN);
  }

  @Test
  void confirmingACodeDoesNotResetTheSendHistory() {
    EmailVerificationStore store = store();
    store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);
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

  // ---- 토큰 조회, 이메일당 토큰 하나 ----

  @Test
  void findTokenEmailReturnsTheEmailOfAValidToken() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(600));

    assertThat(store.findTokenEmail("token-hash", T0.plusSeconds(10))).contains(EMAIL);
  }

  @Test
  void findTokenEmailIsEmptyForUnknownExpiredAndDeletedTokens() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(600));
    store.saveToken("deleted-hash", "other@example.com", T0.plusSeconds(600));
    store.deleteToken("deleted-hash");

    assertThat(store.findTokenEmail("unknown", T0)).isEmpty();
    assertThat(store.findTokenEmail("deleted-hash", T0)).isEmpty();
    assertThat(store.findTokenEmail("token-hash", T0.plusMillis(599_999))).isPresent();
    assertThat(store.findTokenEmail("token-hash", T0.plusSeconds(600))).isEmpty();
  }

  @Test
  void findingATokenDoesNotConsumeIt() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(600));

    assertThat(store.findTokenEmail("token-hash", T0)).isPresent();
    assertThat(store.findTokenEmail("token-hash", T0.plusSeconds(1))).isPresent();
    assertThat(store.hasValidToken("token-hash", EMAIL, T0.plusSeconds(2))).isTrue();
  }

  @Test
  void aNewTokenForTheSameEmailInvalidatesThePreviousOne() {
    EmailVerificationStore store = store();
    store.saveToken("token-a", EMAIL, T0.plusSeconds(600));

    store.saveToken("token-b", EMAIL, T0.plusSeconds(600));

    assertThat(store.hasValidToken("token-a", EMAIL, T0)).isFalse();
    assertThat(store.findTokenEmail("token-a", T0)).isEmpty();
    assertThat(store.hasValidToken("token-b", EMAIL, T0)).isTrue();
    assertThat(store.findTokenEmail("token-b", T0)).contains(EMAIL);
  }

  @Test
  void tokensOfDifferentEmailsAreIndependent() {
    EmailVerificationStore store = store();
    store.saveToken("token-a", "a@example.com", T0.plusSeconds(600));

    store.saveToken("token-b", "b@example.com", T0.plusSeconds(600));

    assertThat(store.findTokenEmail("token-a", T0)).contains("a@example.com");
    assertThat(store.findTokenEmail("token-b", T0)).contains("b@example.com");
  }

  @Test
  void deletingAReplacedTokenDoesNotDeleteTheCurrentOne() {
    EmailVerificationStore store = store();
    store.saveToken("token-a", EMAIL, T0.plusSeconds(600));
    store.saveToken("token-b", EMAIL, T0.plusSeconds(600));

    store.deleteToken("token-a");

    assertThat(store.hasValidToken("token-b", EMAIL, T0)).isTrue();
  }

  @Test
  void aTokenRemembersTheStampItWasSavedWith() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, 7, T0.plusSeconds(600));

    assertThat(store.findToken("token-hash", T0))
        .contains(new EmailVerificationStore.IssuedToken(EMAIL, 7));
  }

  @Test
  void aTokenSavedWithoutAStampHasStampZero() {
    EmailVerificationStore store = store();
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(600));

    assertThat(store.findToken("token-hash", T0))
        .contains(new EmailVerificationStore.IssuedToken(EMAIL, 0));
  }

  @Test
  void findTokenFollowsTheSameValidityRulesAsFindTokenEmail() {
    EmailVerificationStore store = store();
    store.saveToken("token-a", EMAIL, 1, T0.plusSeconds(600));
    store.saveToken("token-b", EMAIL, 2, T0.plusSeconds(600));

    // 교체된 토큰, 만료된 토큰, 없는 토큰은 비어 있다
    assertThat(store.findToken("token-a", T0)).isEmpty();
    assertThat(store.findToken("token-b", T0.plusSeconds(600))).isEmpty();
    assertThat(store.findToken("unknown", T0)).isEmpty();
    assertThat(store.findToken("token-b", T0)).map(t -> t.stamp()).contains(2L);
  }

  @Test
  void savingTheSameTokenAgainKeepsItValid() {
    EmailVerificationStore store = store();
    store.saveToken("token-a", EMAIL, T0.plusSeconds(600));

    store.saveToken("token-a", EMAIL, T0.plusSeconds(1200));

    assertThat(store.hasValidToken("token-a", EMAIL, T0.plusSeconds(900))).isTrue();
  }

  // ---- 이메일 단위 폐기 ----

  @Test
  void invalidateAllRemovesTheTokenAndTheCode() {
    EmailVerificationStore store = store();
    SendPermit permit = store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), permit.generation());
    store.saveToken("token-hash", EMAIL, T0.plusSeconds(600));

    store.invalidateAll(EMAIL);

    assertThat(store.findTokenEmail("token-hash", T0.plusSeconds(1))).isEmpty();
    assertThat(store.confirmCode(EMAIL, "hash-1", T0.plusSeconds(1), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  @Test
  void invalidateAllKeepsTheSendHistory() {
    EmailVerificationStore store = create(Duration.ofSeconds(60), 1);
    SendPermit permit = store.reserveSend(EMAIL, T0);
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), permit.generation());

    store.invalidateAll(EMAIL);

    // 쿨다운과 시간당 한도는 그대로라서 이 호출로 제한을 우회할 수 없다
    assertThat(store.reserveSend(EMAIL, T0.plusSeconds(1)).status())
        .isEqualTo(SendPermit.Status.HOURLY_LIMIT);
  }

  @Test
  void invalidateAllOnlyAffectsTheGivenEmail() {
    EmailVerificationStore store = store();
    store.saveCode("a@example.com", "hash-a", T0.plusSeconds(600), 1);
    store.saveToken("token-a", "a@example.com", T0.plusSeconds(600));
    store.saveCode("b@example.com", "hash-b", T0.plusSeconds(600), 2);
    store.saveToken("token-b", "b@example.com", T0.plusSeconds(600));

    store.invalidateAll("a@example.com");

    assertThat(store.findTokenEmail("token-b", T0)).contains("b@example.com");
    assertThat(store.confirmCode("b@example.com", "hash-b", T0, MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.OK);
  }

  @Test
  void invalidateAllOfAnEmailWithoutStateDoesNothing() {
    EmailVerificationStore store = store();

    store.invalidateAll("nobody@example.com");

    assertThat(store.reserveSend("nobody@example.com", T0).isAllowed()).isTrue();
  }

  // ---- 아무도 맞힐 수 없는 인증번호 (가입 여부를 숨기는 데 쓴다) ----

  @Test
  void aCodeNobodyCanGuessBehavesLikeARealOneUntilItRunsOut() {
    EmailVerificationStore store = store();
    SendPermit permit = store.reserveSend(EMAIL, T0);
    store.saveCode(
        EMAIL, "decoy-" + java.util.UUID.randomUUID(), T0.plusSeconds(600), permit.generation());

    for (int i = 0; i < MAX_ATTEMPTS; i++) {
      assertThat(store.confirmCode(EMAIL, "any-code-" + i, T0.plusSeconds(1), MAX_ATTEMPTS))
          .isEqualTo(ConfirmOutcome.MISMATCH);
    }
    assertThat(store.confirmCode(EMAIL, "any-code", T0.plusSeconds(2), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.ATTEMPTS_EXCEEDED);
  }

  @Test
  void aCodeNobodyCanGuessExpiresLikeARealOne() {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "decoy-" + java.util.UUID.randomUUID(), T0.plusSeconds(600), 1);

    assertThat(store.confirmCode(EMAIL, "any-code", T0.plusSeconds(599), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.MISMATCH);
    assertThat(store.confirmCode(EMAIL, "any-code", T0.plusSeconds(600), MAX_ATTEMPTS))
        .isEqualTo(ConfirmOutcome.EXPIRED_OR_MISSING);
  }

  // ---- 동시성 ----

  @Test
  void concurrentWrongCodesCountEveryAttempt() throws Exception {
    EmailVerificationStore store = store();
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

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
    store.saveCode(EMAIL, "hash-1", T0.plusSeconds(600), 1);

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

  @Test
  void concurrentTokenSavesForOneEmailLeaveExactlyOneValidToken() throws Exception {
    EmailVerificationStore store = store();
    int threads = 32;
    AtomicInteger sequence = new AtomicInteger();

    runConcurrently(
        threads,
        () -> {
          store.saveToken("token-" + sequence.incrementAndGet(), EMAIL, T0.plusSeconds(600));
          return null;
        });

    long valid =
        IntStream.rangeClosed(1, threads)
            .filter(i -> store.hasValidToken("token-" + i, EMAIL, T0))
            .count();
    assertThat(valid).isEqualTo(1);
    // 유효한 토큰은 조회로도 같은 이메일을 가리킨다
    assertThat(
            IntStream.rangeClosed(1, threads)
                .filter(i -> store.findTokenEmail("token-" + i, T0).isPresent())
                .count())
        .isEqualTo(1);
  }

  @Test
  void mixedTokenOperationsNeverLeaveMoreThanOneValidTokenPerEmail() throws Exception {
    EmailVerificationStore store = store();
    int threads = 8;
    int rounds = 400;
    int tokens = 16;
    AtomicInteger sequence = new AtomicInteger();

    runConcurrently(
        threads,
        () -> {
          int seed = sequence.incrementAndGet();
          for (int r = 0; r < rounds; r++) {
            String hash = "token-" + ((seed * 31 + r) % tokens);
            switch (r % 4) {
              case 0 -> store.saveToken(hash, EMAIL, T0.plusSeconds(600));
              case 1 -> store.findTokenEmail(hash, T0);
              case 2 -> store.deleteToken(hash);
              default -> store.hasValidToken(hash, EMAIL, T0);
            }
            if (r % 97 == 0) {
              store.invalidateAll(EMAIL);
            }
          }
          return null;
        });

    long valid =
        IntStream.range(0, tokens)
            .filter(i -> store.findTokenEmail("token-" + i, T0).isPresent())
            .count();
    assertThat(valid).isLessThanOrEqualTo(1);
  }

  @Test
  void concurrentReservationsGetDistinctGenerations() throws Exception {
    EmailVerificationStore store = create(Duration.ZERO, 1_000);

    List<SendPermit> permits = runConcurrently(64, () -> store.reserveSend(EMAIL, T0));

    assertThat(permits.stream().map(SendPermit::generation).distinct().count()).isEqualTo(64);
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
