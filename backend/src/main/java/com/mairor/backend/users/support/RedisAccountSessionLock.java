package com.mairor.backend.users.support;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

/**
 * 한 계정의 로그인을 서버 여러 대에 걸쳐 하나씩 처리한다(계정당 로그인 세션 1개). 잠금을 3초 안에 얻지 못하면 429 {@code TOO_MANY_REQUESTS}
 * (Retry-After: 1), 기다리는 중에 서버가 내려가면 503 {@code SERVICE_UNAVAILABLE} 이다. 잠금은 2분 뒤 저절로 풀린다.
 */
@Component
public class RedisAccountSessionLock {

  private static final Logger log = LoggerFactory.getLogger(RedisAccountSessionLock.class);
  private static final Duration LEASE = Duration.ofMinutes(2);
  private static final Duration WAIT = Duration.ofSeconds(3);
  private static final long RETRY_MILLIS = 25;
  private static final String KEY_PREFIX = "mairor:auth:account-login-lock:";
  private static final DefaultRedisScript<Long> RELEASE =
      new DefaultRedisScript<>(
          "if redis.call('get', KEYS[1]) == ARGV[1] then "
              + "return redis.call('del', KEYS[1]) else return 0 end",
          Long.class);

  private final StringRedisTemplate redis;

  public RedisAccountSessionLock(StringRedisTemplate redis) {
    this.redis = redis;
  }

  public <T> T withLock(UUID userId, Supplier<T> action) {
    String key = KEY_PREFIX + userId;
    String token = UUID.randomUUID().toString();
    long deadline = System.nanoTime() + WAIT.toNanos();
    while (!acquire(key, token)) {
      if (System.nanoTime() >= deadline) {
        throw BusinessException.tooManyRequests(1);
      }
      try {
        Thread.sleep(RETRY_MILLIS);
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new BusinessException(ErrorCode.SERVICE_UNAVAILABLE);
      }
    }

    try {
      return action.get();
    } finally {
      release(key, token);
    }
  }

  private boolean acquire(String key, String token) {
    return Boolean.TRUE.equals(redis.opsForValue().setIfAbsent(key, token, LEASE));
  }

  private void release(String key, String token) {
    try {
      redis.execute(RELEASE, List.of(key), token);
    } catch (RuntimeException e) {
      // 잠금은 저절로 풀리므로, 이미 끝난 로그인을 해제 실패 때문에 오류로 바꾸지 않는다
      log.warn("계정 로그인 잠금을 풀지 못했습니다. 만료되면 저절로 풀립니다");
      log.debug("계정 로그인 잠금 해제 실패", e);
    }
  }
}
