package com.mairor.backend.users.support;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 로그인 시도 제한. 이메일마다 진행 중인 시도와 확정된 실패를 따로 센다. {@code 확정 실패 + 진행 중 시도 ≤ maxFailures} 가 항상 유지되도록 시도를
 * 시작할 때 자리(슬롯)를 잡고, 확정 실패가 {@code maxFailures} 에 닿으면 잠근다. 올바른 비밀번호로 성공하면 확정 실패를 지운다.
 *
 * <p>{@link #tryAcquire} 가 준 {@link Ticket} 은 성공({@link #succeed})·실패({@link #fail})·환불({@link
 * #refund}) 중 정확히 한 번만 종료한다. 자격 증명과 무관한 내부 오류나 BCrypt 상한 거절은 환불해 실패로 세지 않는다. 호출자는 어떤 경로에서도 ticket 을
 * 종료해야 한다. 현재 시각은 호출자가 넘기며, 모든 메서드는 이메일 단위로 원자적이어야 한다.
 */
public interface LoginAttemptLimiter {

  /** 시도를 시작할 수 있는지 판정하고, 가능하면 자리를 잡아 ticket 을 준다. */
  Result tryAcquire(String email, Instant now);

  /** 올바른 비밀번호로 성공했다. 자리를 반환하고 확정 실패를 지운다. */
  void succeed(Ticket ticket);

  /** 비밀번호가 틀렸다. 자리를 반환하고 확정 실패를 늘리며, 임계치에 닿으면 잠근다. */
  void fail(Ticket ticket, Instant now);

  /** 실패로 세지 않을 시도를 취소한다. 자리만 반환한다. */
  void refund(Ticket ticket);

  /**
   * 이메일의 확정 실패와 잠금을 지운다(비밀번호 재설정 성공 시). 진행 중인 시도는 건드리지 않아서 그 자리는 계속 차지하고, 끝나면 평소처럼 센다. 상태가 없는 이메일이면
   * 아무 일도 하지 않는다. 호출자는 {@code tryAcquire} 에 넘기는 것과 같은 정규화 이메일을 넘겨야 한다.
   */
  void reset(String email);

  /** {@link #tryAcquire} 결과. */
  sealed interface Result permits Allowed, Locked, Pending, Saturated {}

  /** 시도해도 된다. 반드시 {@code ticket} 을 종료해야 한다. */
  record Allowed(Ticket ticket) implements Result {}

  /** 이메일이 잠겨 있다. 비밀번호가 맞아도 거절한다. */
  record Locked(long retryAfterSeconds) implements Result {}

  /** 이 이메일의 자리가 진행 중인 시도로 가득 찼다. 잠시 뒤 다시 시도한다. */
  record Pending(long retryAfterSeconds) implements Result {}

  /** 상태 저장소가 가득 차서 새 이메일을 받을 수 없다. */
  record Saturated(long retryAfterSeconds) implements Result {}

  /**
   * 시도 하나의 표지. 이메일과, 그 이메일 상태 인스턴스를 구분하는 {@code epoch} 를 가진다. 상태가 사라졌다 다시 만들어져도 예전 ticket 이 새 상태를
   * 바꾸지 못하도록 {@code epoch} 가 다르면 종료 호출을 무시한다.
   */
  final class Ticket {

    private final String email;
    private final long epoch;
    private final AtomicBoolean closed = new AtomicBoolean();

    Ticket(String email, long epoch) {
      this.email = email;
      this.epoch = epoch;
    }

    public String email() {
      return email;
    }

    public long epoch() {
      return epoch;
    }

    /** 처음 호출할 때만 {@code true}. 한 ticket 은 한 번만 종료된다. */
    boolean close() {
      return closed.compareAndSet(false, true);
    }
  }
}
