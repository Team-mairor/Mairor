package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

class PasswordResetLocksTest {

  /** 다른 스레드에서 잡아 본다. 같은 스레드는 다시 잡을 수 있어서(재진입) 경쟁을 흉내 내지 못한다. */
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
  void theSameEmailCannotBeLockedTwiceAtOnce() throws Exception {
    PasswordResetLocks locks = new PasswordResetLocks();

    try (var held = locks.tryLock("a@x.com").orElseThrow()) {
      assertThat(canLockFromAnotherThread(locks, "a@x.com")).isFalse();
    }

    assertThat(canLockFromAnotherThread(locks, "a@x.com")).isTrue();
  }

  @Test
  void differentEmailsOnDifferentStripesDoNotBlockEachOther() throws Exception {
    PasswordResetLocks locks = new PasswordResetLocks(2);
    String a = "a@x.com";
    String b = findEmailOnTheOtherStripe(a, 2);

    try (var held = locks.tryLock(a).orElseThrow()) {
      assertThat(canLockFromAnotherThread(locks, b)).isTrue();
    }
  }

  @Test
  void differentEmailsSharingAStripeBlockEachOther() throws Exception {
    // 잠금이 하나뿐이면 모든 이메일이 같은 칸을 쓴다: 드물게 생기는 불필요한 거절이 이런 경우다
    PasswordResetLocks locks = new PasswordResetLocks(1);

    try (var held = locks.tryLock("a@x.com").orElseThrow()) {
      assertThat(canLockFromAnotherThread(locks, "b@x.com")).isFalse();
    }
  }

  @Test
  void closingTwiceReleasesOnlyOnce() throws Exception {
    PasswordResetLocks locks = new PasswordResetLocks(1);
    var held = locks.tryLock("a@x.com").orElseThrow();

    held.close();
    held.close();

    assertThat(canLockFromAnotherThread(locks, "a@x.com")).isTrue();
  }

  @Test
  void theLockIsReleasedWhenTheGuardedCodeThrows() throws Exception {
    PasswordResetLocks locks = new PasswordResetLocks();

    assertThatThrownBy(
            () -> {
              try (var held = locks.tryLock("a@x.com").orElseThrow()) {
                throw new IllegalStateException("boom");
              }
            })
        .isInstanceOf(IllegalStateException.class);

    assertThat(canLockFromAnotherThread(locks, "a@x.com")).isTrue();
  }

  @Test
  void rejectsAnInvalidStripeCount() {
    assertThatThrownBy(() -> new PasswordResetLocks(0))
        .isInstanceOf(IllegalArgumentException.class);
  }

  private static String findEmailOnTheOtherStripe(String email, int stripes) {
    int stripe = Math.floorMod(email.hashCode(), stripes);
    for (int i = 0; ; i++) {
      String candidate = "b" + i + "@x.com";
      if (Math.floorMod(candidate.hashCode(), stripes) != stripe) {
        return candidate;
      }
    }
  }
}
