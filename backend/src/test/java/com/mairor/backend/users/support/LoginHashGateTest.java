package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.users.support.LoginHashGate.Permit;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class LoginHashGateTest {

  @Test
  void admitsUpToTheLimitThenRejectsImmediately() {
    LoginHashGate gate = new LoginHashGate(2);

    Optional<Permit> first = gate.tryEnter();
    Optional<Permit> second = gate.tryEnter();

    assertThat(first).isPresent();
    assertThat(second).isPresent();
    assertThat(gate.tryEnter()).isEmpty();
  }

  @Test
  void closingAPermitFreesTheSlot() {
    LoginHashGate gate = new LoginHashGate(1);
    Permit permit = gate.tryEnter().orElseThrow();
    assertThat(gate.tryEnter()).isEmpty();

    permit.close();

    assertThat(gate.tryEnter()).isPresent();
  }

  @Test
  void closingTwiceReleasesOnlyOnce() {
    LoginHashGate gate = new LoginHashGate(1);
    Permit permit = gate.tryEnter().orElseThrow();

    permit.close();
    permit.close();

    assertThat(gate.availablePermits()).isEqualTo(1);
  }

  @Test
  void releasesTheSlotWhenTheGuardedCodeThrows() {
    LoginHashGate gate = new LoginHashGate(1);

    assertThatThrownBy(
            () -> {
              try (Permit ignored = gate.tryEnter().orElseThrow()) {
                throw new IllegalStateException("해시 계산 실패");
              }
            })
        .isInstanceOf(IllegalStateException.class);

    assertThat(gate.availablePermits()).isEqualTo(1);
  }

  @Test
  void concurrentEntrantsNeverExceedTheLimit() throws Exception {
    int limit = 4;
    int threads = 64;
    LoginHashGate gate = new LoginHashGate(limit);
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch ready = new CountDownLatch(threads);
    CountDownLatch go = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    AtomicInteger admitted = new AtomicInteger();
    AtomicInteger rejected = new AtomicInteger();
    try {
      List<Future<?>> futures = new ArrayList<>();
      for (int i = 0; i < threads; i++) {
        futures.add(
            pool.submit(
                () -> {
                  ready.countDown();
                  go.await();
                  Optional<Permit> permit = gate.tryEnter();
                  if (permit.isPresent()) {
                    admitted.incrementAndGet();
                    // 모두가 시도를 끝낼 때까지 자리를 쥐고 있는다
                    release.await();
                    permit.get().close();
                  } else {
                    rejected.incrementAndGet();
                  }
                  return null;
                }));
      }
      assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
      go.countDown();
      long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
      while (admitted.get() + rejected.get() < threads && System.nanoTime() < deadline) {
        Thread.onSpinWait();
      }
      assertThat(admitted.get()).isEqualTo(limit);
      assertThat(rejected.get()).isEqualTo(threads - limit);
      release.countDown();
      for (Future<?> future : futures) {
        future.get(30, TimeUnit.SECONDS);
      }
    } finally {
      release.countDown();
      pool.shutdownNow();
    }

    assertThat(gate.availablePermits()).isEqualTo(limit);
  }

  @Test
  void rejectsAnInvalidLimit() {
    assertThatThrownBy(() -> new LoginHashGate(0)).isInstanceOf(IllegalArgumentException.class);
  }
}
