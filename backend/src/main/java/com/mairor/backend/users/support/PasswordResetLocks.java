package com.mairor.backend.users.support;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

/**
 * 비밀번호 재설정의 이메일 단위 잠금. 같은 이메일의 재설정 요청을 한 번에 하나만 실행해서, 늦게 도착한 요청이 다른 요청이 정리한 상태를 되살리거나 같은 토큰으로 비밀번호를
 * 두 번 바꾸지 못하게 한다.
 *
 * <p>기다리지 않는다. 잡혀 있으면 호출자가 바로 429 로 거절해서 요청 스레드가 쌓이지 않는다. Redis 구현은 정규화 이메일별로 잠그고, 프로세스 종료 뒤 잠금이 남지
 * 않도록 제한 시간 후 자동 만료한다.
 */
public class PasswordResetLocks {

  private static final int STRIPES = 256;
  private static final Duration LEASE = Duration.ofMinutes(5);
  private static final String KEY_PREFIX = "mairor:auth:password-reset-lock:";
  private static final Logger log = LoggerFactory.getLogger(PasswordResetLocks.class);
  private static final DefaultRedisScript<Long> RELEASE =
      new DefaultRedisScript<>(
          "if redis.call('get', KEYS[1]) == ARGV[1] then "
              + "return redis.call('del', KEYS[1]) else return 0 end",
          Long.class);

  private final ReentrantLock[] locks;
  private final StringRedisTemplate redis;

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
    this.redis = null;
  }

  public PasswordResetLocks(StringRedisTemplate redis) {
    this.redis = redis;
    this.locks = null;
  }

  /**
   * 정규화한 이메일의 잠금을 기다리지 않고 잡아 본다.
   *
   * @return 잡았으면 닫아서 푸는 손잡이, 다른 요청이 잡고 있으면 비어 있다
   */
  public Optional<Held> tryLock(String email) {
    if (redis != null) {
      String key = KEY_PREFIX + hash(email);
      String token = UUID.randomUUID().toString();
      boolean acquired = Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(key, token, LEASE));
      return acquired ? Optional.of(new Held(() -> release(key, token))) : Optional.empty();
    }
    ReentrantLock lock = locks[Math.floorMod(email.hashCode(), locks.length)];
    return lock.tryLock() ? Optional.of(new Held(lock::unlock)) : Optional.empty();
  }

  private void release(String key, String token) {
    try {
      redis.execute(RELEASE, List.of(key), token);
    } catch (RuntimeException e) {
      log.warn("Could not release password reset lock; it will expire automatically");
      log.debug("Password reset lock release failed", e);
    }
  }

  private static String hash(String email) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(email.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is unavailable", e);
    }
  }

  /** 잡은 잠금. {@code try-with-resources} 로 잡은 스레드에서 닫는다. 여러 번 닫아도 한 번만 푼다. */
  public static final class Held implements AutoCloseable {

    private final Runnable release;
    private final AtomicBoolean released = new AtomicBoolean();

    private Held(Runnable release) {
      this.release = release;
    }

    @Override
    public void close() {
      if (released.compareAndSet(false, true)) {
        release.run();
      }
    }
  }
}
