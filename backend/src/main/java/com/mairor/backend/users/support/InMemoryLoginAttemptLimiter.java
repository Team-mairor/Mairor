package com.mairor.backend.users.support;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Consumer;

/**
 * 인메모리 {@link LoginAttemptLimiter}. 하나의 락 안에서 삽입 순서가 있는 맵 두 개를 다루며 모든 연산이 상각 O(1) 이다. 오래된 항목을 찾으려고
 * 맵 전체를 순회하지 않는다.
 *
 * <ul>
 *   <li>{@code active}: 잠기지 않은 이메일의 상태. 접근 순서로 정렬돼 머리가 가장 오래 쓰이지 않은 항목이다.
 *   <li>{@code locked}: 잠긴 이메일. 잠금 시간이 고정이라 삽입 순서가 곧 해제 순서이므로 머리에서만 만료 항목을 지운다.
 * </ul>
 *
 * <p>진행 중인 시도가 있는 상태는 시간이 지나거나 용량이 차도 지우지 않는다. 그래서 확정 실패와 진행 중 시도의 합이 임계치를 넘지 않는다는 불변식이 유지되고, 잠금이
 * 걸리는 순간에는 진행 중인 시도가 없다.
 *
 * <p>한계: 서버마다 따로 세며 재시작하면 초기화된다.
 */
public class InMemoryLoginAttemptLimiter implements LoginAttemptLimiter {

  private static final Duration SUMMARY_INTERVAL = Duration.ofMinutes(1);
  private static final long PENDING_RETRY_SECONDS = 1;

  private static final class Attempts {
    final long epoch;
    int failures;
    int inFlight;
    Instant lastAttempt;

    Attempts(long epoch, Instant now) {
      this.epoch = epoch;
      this.lastAttempt = now;
    }
  }

  private record LockedEntry(Instant until) {}

  private final int maxFailures;
  private final Duration lockDuration;
  private final Duration attemptTtl;
  private final int maxEntries;
  private final Consumer<String> summarySink;

  private final ReentrantLock lock = new ReentrantLock();
  private final LinkedHashMap<String, Attempts> active = new LinkedHashMap<>(16, 0.75f, true);
  private final LinkedHashMap<String, LockedEntry> locked = new LinkedHashMap<>();
  private long epochSequence;
  private long evictions;
  private long rejections;
  private Instant lastSummary;

  /**
   * @param summarySink 용량 때문에 제거하거나 거절한 횟수를 모아 최대 1분에 한 번 넘겨 받는 요약 메시지 (요청마다 로그를 남기지 않기 위해)
   */
  public InMemoryLoginAttemptLimiter(
      int maxFailures,
      Duration lockDuration,
      Duration attemptTtl,
      int maxEntries,
      Consumer<String> summarySink) {
    if (maxFailures < 1) {
      throw new IllegalArgumentException("maxFailures 는 1 이상이어야 합니다: " + maxFailures);
    }
    if (lockDuration.isZero() || lockDuration.isNegative()) {
      throw new IllegalArgumentException("lockDuration 은 0보다 길어야 합니다: " + lockDuration);
    }
    if (attemptTtl.isZero() || attemptTtl.isNegative()) {
      throw new IllegalArgumentException("attemptTtl 은 0보다 길어야 합니다: " + attemptTtl);
    }
    if (maxEntries < 1) {
      throw new IllegalArgumentException("maxEntries 는 1 이상이어야 합니다: " + maxEntries);
    }
    this.maxFailures = maxFailures;
    this.lockDuration = lockDuration;
    this.attemptTtl = attemptTtl;
    this.maxEntries = maxEntries;
    this.summarySink = summarySink;
  }

  @Override
  public Result tryAcquire(String email, Instant now) {
    lock.lock();
    try {
      purge(now);
      Result result = acquire(email, now);
      summarize(now);
      return result;
    } finally {
      lock.unlock();
    }
  }

  private Result acquire(String email, Instant now) {
    LockedEntry lockedEntry = locked.get(email);
    if (lockedEntry != null) {
      if (now.isBefore(lockedEntry.until())) {
        return new Locked(secondsUntil(lockedEntry.until(), now));
      }
      locked.remove(email);
    }
    Attempts attempts = active.get(email);
    if (attempts == null) {
      if (!makeRoom()) {
        rejections++;
        return new Saturated(earliestUnlockSeconds(now));
      }
      attempts = new Attempts(++epochSequence, now);
      active.put(email, attempts);
    }
    if (attempts.failures + attempts.inFlight >= maxFailures) {
      return new Pending(PENDING_RETRY_SECONDS);
    }
    attempts.inFlight++;
    attempts.lastAttempt = now;
    return new Allowed(new Ticket(email, attempts.epoch));
  }

  @Override
  public void succeed(Ticket ticket) {
    if (!ticket.close()) {
      return;
    }
    lock.lock();
    try {
      Attempts attempts = ownedAttempts(ticket);
      if (attempts == null) {
        return;
      }
      attempts.inFlight--;
      attempts.failures = 0;
      removeIfIdle(ticket.email(), attempts);
    } finally {
      lock.unlock();
    }
  }

  @Override
  public void fail(Ticket ticket, Instant now) {
    if (!ticket.close()) {
      return;
    }
    lock.lock();
    try {
      Attempts attempts = ownedAttempts(ticket);
      if (attempts == null) {
        return;
      }
      attempts.inFlight--;
      attempts.failures++;
      attempts.lastAttempt = now;
      if (attempts.failures >= maxFailures) {
        active.remove(ticket.email());
        locked.put(ticket.email(), new LockedEntry(now.plus(lockDuration)));
      }
    } finally {
      lock.unlock();
    }
  }

  @Override
  public void refund(Ticket ticket) {
    if (!ticket.close()) {
      return;
    }
    lock.lock();
    try {
      Attempts attempts = ownedAttempts(ticket);
      if (attempts == null) {
        return;
      }
      attempts.inFlight--;
      removeIfIdle(ticket.email(), attempts);
    } finally {
      lock.unlock();
    }
  }

  /** ticket 이 가리키는 상태. 상태가 없거나 다른 인스턴스(epoch 다름)면 {@code null}. */
  private Attempts ownedAttempts(Ticket ticket) {
    Attempts attempts = active.get(ticket.email());
    if (attempts == null || attempts.epoch != ticket.epoch()) {
      return null;
    }
    return attempts;
  }

  private void removeIfIdle(String email, Attempts attempts) {
    if (attempts.failures == 0 && attempts.inFlight == 0) {
      active.remove(email);
    }
  }

  /** 만료된 잠금과 오래 쓰이지 않은 상태를 머리에서부터 지운다. */
  private void purge(Instant now) {
    var lockedIterator = locked.values().iterator();
    while (lockedIterator.hasNext()) {
      if (now.isBefore(lockedIterator.next().until())) {
        break;
      }
      lockedIterator.remove();
    }
    var activeIterator = active.values().iterator();
    while (activeIterator.hasNext()) {
      Attempts attempts = activeIterator.next();
      if (now.isBefore(attempts.lastAttempt.plus(attemptTtl))) {
        break;
      }
      if (attempts.inFlight == 0) {
        activeIterator.remove();
      }
    }
  }

  /** 새 이메일을 넣을 자리를 만든다. 진행 중인 시도가 없는 가장 오래된 상태를 지우며, 지울 것이 없으면 {@code false}. */
  private boolean makeRoom() {
    if (active.size() + locked.size() < maxEntries) {
      return true;
    }
    var iterator = active.values().iterator();
    while (iterator.hasNext()) {
      if (iterator.next().inFlight == 0) {
        iterator.remove();
        evictions++;
        return true;
      }
    }
    return false;
  }

  private long earliestUnlockSeconds(Instant now) {
    var iterator = locked.values().iterator();
    if (!iterator.hasNext()) {
      return PENDING_RETRY_SECONDS;
    }
    return secondsUntil(iterator.next().until(), now);
  }

  private void summarize(Instant now) {
    if (evictions + rejections == 0) {
      return;
    }
    if (lastSummary != null && now.isBefore(lastSummary.plus(SUMMARY_INTERVAL))) {
      return;
    }
    summarySink.accept(
        "로그인 시도 제한 저장소가 가득 찼습니다: 용량 초과로 제거 "
            + evictions
            + "건, 신규 이메일 거절 "
            + rejections
            + "건 (maxEntries="
            + maxEntries
            + ")");
    evictions = 0;
    rejections = 0;
    lastSummary = now;
  }

  /** 남은 시간을 올림한 초. 항상 1 이상이라 {@code Retry-After: 0} 이 나가지 않는다. */
  private static long secondsUntil(Instant end, Instant now) {
    long millis = Duration.between(now, end).toMillis();
    return Math.max(1, (millis + 999) / 1000);
  }
}
