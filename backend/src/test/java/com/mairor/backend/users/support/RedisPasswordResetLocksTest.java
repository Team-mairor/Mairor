package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.testsupport.RedisTestServer;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/** Redis 잠금은 서버 여러 대가 같은 이메일의 재설정을 동시에 진행하지 못하게 한다. 서버 두 대를 잠금 객체 두 개로 흉내 낸다. */
class RedisPasswordResetLocksTest {

  private PasswordResetLocks serverA;
  private PasswordResetLocks serverB;

  @BeforeEach
  void setUp() {
    RedisTestServer.flush();
    serverA = new PasswordResetLocks(RedisTestServer.template());
    serverB = new PasswordResetLocks(RedisTestServer.template());
  }

  private static boolean canLockFromAnotherThread(PasswordResetLocks locks, String email)
      throws Exception {
    return CompletableFuture.supplyAsync(
            () -> {
              Optional<PasswordResetLocks.Held> held = locks.tryLock(email);
              held.ifPresent(PasswordResetLocks.Held::close);
              return held.isPresent();
            })
        .get(10, TimeUnit.SECONDS);
  }

  @Test
  void anotherServerCannotLockTheSameEmailUntilItIsReleased() throws Exception {
    try (var held = serverA.tryLock("a@x.com").orElseThrow()) {
      assertThat(canLockFromAnotherThread(serverB, "a@x.com")).isFalse();
    }

    assertThat(canLockFromAnotherThread(serverB, "a@x.com")).isTrue();
  }

  @Test
  void differentEmailsDoNotBlockEachOtherAcrossServers() throws Exception {
    try (var held = serverA.tryLock("a@x.com").orElseThrow()) {
      assertThat(canLockFromAnotherThread(serverB, "b@x.com")).isTrue();
    }
  }

  @Test
  void closingTwiceDoesNotReleaseALockTakenByAnotherServer() throws Exception {
    var first = serverA.tryLock("a@x.com").orElseThrow();
    first.close();
    var second = serverB.tryLock("a@x.com").orElseThrow();

    first.close();

    assertThat(canLockFromAnotherThread(serverA, "a@x.com")).isFalse();
    second.close();
  }

  @Test
  void theLockIsReleasedWhenTheGuardedCodeThrows() throws Exception {
    assertThatThrownBy(
            () -> {
              try (var held = serverA.tryLock("a@x.com").orElseThrow()) {
                throw new IllegalStateException("boom");
              }
            })
        .isInstanceOf(IllegalStateException.class);

    assertThat(canLockFromAnotherThread(serverB, "a@x.com")).isTrue();
  }
}
