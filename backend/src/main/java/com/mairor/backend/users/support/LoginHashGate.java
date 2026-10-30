package com.mairor.backend.users.support;

import java.util.Optional;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 로그인 BCrypt 계산의 서버 전체 동시 실행 상한. 미가입 이메일도 더미 해시를 계산하므로 서로 다른 이메일을 계속 보내면 이메일 단위 제한이 걸리지 않고 CPU 가
 * 소진된다. 그걸 막으려고 동시에 계산하는 수를 제한한다.
 *
 * <p>자리가 없으면 기다리지 않고 바로 거절한다. 대기열을 두면 요청이 쌓여 스레드와 메모리를 쓴다. 가상 스레드를 써도 CPU 비용은 줄지 않는다.
 */
public class LoginHashGate {

  private final Semaphore semaphore;

  public LoginHashGate(int maxConcurrent) {
    if (maxConcurrent < 1) {
      throw new IllegalArgumentException("maxConcurrent 는 1 이상이어야 합니다: " + maxConcurrent);
    }
    this.semaphore = new Semaphore(maxConcurrent);
  }

  /** 자리가 있으면 {@link Permit} 을, 없으면 빈 값을 즉시 돌려준다. {@code try-with-resources} 로 반드시 반환한다. */
  public Optional<Permit> tryEnter() {
    return semaphore.tryAcquire() ? Optional.of(new Permit(semaphore)) : Optional.empty();
  }

  /** 지금 비어 있는 자리 수. */
  public int availablePermits() {
    return semaphore.availablePermits();
  }

  /** 자리 하나. {@link #close()} 를 여러 번 불러도 한 번만 반환한다. */
  public static final class Permit implements AutoCloseable {

    private final Semaphore semaphore;
    private final AtomicBoolean released = new AtomicBoolean();

    private Permit(Semaphore semaphore) {
      this.semaphore = semaphore;
    }

    @Override
    public void close() {
      if (released.compareAndSet(false, true)) {
        semaphore.release();
      }
    }
  }
}
