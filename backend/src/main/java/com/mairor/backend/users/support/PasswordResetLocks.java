package com.mairor.backend.users.support;

import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.stereotype.Component;

/**
 * 비밀번호 재설정의 이메일 단위 잠금. 같은 이메일의 재설정 요청을 한 번에 하나만 실행해서, 늦게 도착한 요청이 다른 요청이 정리한 상태를 되살리거나 같은 토큰으로 비밀번호를
 * 두 번 바꾸지 못하게 한다.
 *
 * <p>기다리지 않는다. 잡혀 있으면 호출자가 바로 429 로 거절해서 요청 스레드가 쌓이지 않는다. 고정된 개수의 잠금을 이메일 해시로 나눠 쓰므로, 서로 다른 이메일이 같은
 * 잠금에 걸려 드물게 불필요한 거절이 생긴다(다시 보내면 통과한다). 프로세스 안에서만 유효하다(서버가 여러 대면 분산 잠금이 필요하다).
 */
@Component
public class PasswordResetLocks {

  private static final int STRIPES = 256;

  private final ReentrantLock[] locks;

  public PasswordResetLocks() {
    this(STRIPES);
  }

  PasswordResetLocks(int stripes) {
    if (stripes < 1) {
      throw new IllegalArgumentException("잠금 개수는 1 이상이어야 합니다: " + stripes);
    }
    locks = new ReentrantLock[stripes];
    for (int i = 0; i < stripes; i++) {
      locks[i] = new ReentrantLock();
    }
  }

  /**
   * 정규화한 이메일의 잠금을 기다리지 않고 잡아 본다.
   *
   * @return 잡았으면 닫아서 푸는 손잡이, 다른 요청이 잡고 있으면 비어 있다
   */
  public Optional<Held> tryLock(String email) {
    ReentrantLock lock = locks[Math.floorMod(email.hashCode(), locks.length)];
    return lock.tryLock() ? Optional.of(new Held(lock)) : Optional.empty();
  }

  /** 잡은 잠금. {@code try-with-resources} 로 잡은 스레드에서 닫는다. 여러 번 닫아도 한 번만 푼다. */
  public static final class Held implements AutoCloseable {

    private final ReentrantLock lock;
    private final AtomicBoolean released = new AtomicBoolean();

    private Held(ReentrantLock lock) {
      this.lock = lock;
    }

    @Override
    public void close() {
      if (released.compareAndSet(false, true)) {
        lock.unlock();
      }
    }
  }
}
