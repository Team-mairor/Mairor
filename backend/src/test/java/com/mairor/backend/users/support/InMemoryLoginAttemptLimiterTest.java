package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.users.support.LoginAttemptLimiter.Allowed;
import com.mairor.backend.users.support.LoginAttemptLimiter.Pending;
import com.mairor.backend.users.support.LoginAttemptLimiter.Ticket;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class InMemoryLoginAttemptLimiterTest extends LoginAttemptLimiterContract {

  @Override
  protected LoginAttemptLimiter create(
      int maxFailures, Duration lockDuration, Duration attemptTtl, int maxEntries) {
    return new InMemoryLoginAttemptLimiter(
        maxFailures, lockDuration, attemptTtl, maxEntries, message -> {});
  }

  @Test
  void keepsAStateWhileAnAttemptIsStillInFlight() {
    LoginAttemptLimiter limiter = create(1, Duration.ofSeconds(30), Duration.ofMinutes(15), 1_000);
    acquire(limiter, "a@x.com", T0);

    // TTL 이 한참 지나도 진행 중인 시도가 있으면 자리를 잡고 있다
    assertThat(limiter.tryAcquire("a@x.com", T0.plus(Duration.ofHours(1))))
        .isInstanceOf(Pending.class);
  }

  @Test
  void ignoresATicketFromAnotherStateInstance() {
    LoginAttemptLimiter limiter = create(2, Duration.ofSeconds(30), Duration.ofMinutes(15), 10);
    acquire(limiter, "a@x.com");
    // epoch 가 다른(예전 상태에서 발급된) ticket 은 어떤 종료 호출도 새 상태를 바꾸지 못한다
    limiter.succeed(new Ticket("a@x.com", 999));
    limiter.fail(new Ticket("a@x.com", 998), T0);
    limiter.refund(new Ticket("a@x.com", 997));

    // 진짜 ticket 한 개가 열려 있고 둘째는 허용, 셋째는 자리가 없다
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Allowed.class);
    assertThat(limiter.tryAcquire("a@x.com", T0)).isInstanceOf(Pending.class);
  }

  @Test
  void summarizesEvictionsAtMostOncePerMinuteWithoutLoggingEmails() {
    List<String> messages = new ArrayList<>();
    LoginAttemptLimiter limiter =
        new InMemoryLoginAttemptLimiter(
            3, Duration.ofSeconds(30), Duration.ofMinutes(15), 2, messages::add);
    for (int i = 0; i < 10; i++) {
      var ticket = acquire(limiter, "user" + i + "@x.com");
      limiter.fail(ticket, T0.plusSeconds(i));
    }

    // 제거가 여러 번 일어나도 한 번만 요약하고, 이메일은 남기지 않는다
    assertThat(messages).hasSize(1);
    assertThat(messages.get(0)).doesNotContain("user").doesNotContain("@");

    limiter.tryAcquire("another@x.com", T0.plusSeconds(61));
    assertThat(messages).hasSize(2);
  }

  @Test
  void rejectsInvalidSettings() {
    Duration ok = Duration.ofSeconds(30);
    assertThatThrownBy(() -> new InMemoryLoginAttemptLimiter(0, ok, ok, 1, m -> {}))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new InMemoryLoginAttemptLimiter(1, Duration.ZERO, ok, 1, m -> {}))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> new InMemoryLoginAttemptLimiter(1, ok, Duration.ofSeconds(-1), 1, m -> {}))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new InMemoryLoginAttemptLimiter(1, ok, ok, 0, m -> {}))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private static Ticket acquire(LoginAttemptLimiter limiter, String email) {
    return ((Allowed) limiter.tryAcquire(email, T0)).ticket();
  }
}
