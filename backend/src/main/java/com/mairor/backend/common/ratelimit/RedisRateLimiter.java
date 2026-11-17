package com.mairor.backend.common.ratelimit;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

/** Redis-backed fixed-window rate limiter shared by all backend instances. */
public class RedisRateLimiter implements RateLimiter {

  private static final String KEY_PREFIX = "mairor:rate-limit:";
  private static final DefaultRedisScript<List> ACQUIRE =
      new DefaultRedisScript<>(
          "local now = tonumber(ARGV[1]) "
              + "local window = tonumber(ARGV[2]) "
              + "local limit = tonumber(ARGV[3]) "
              + "local start = tonumber(redis.call('HGET', KEYS[1], 'start')) "
              + "local count = tonumber(redis.call('HGET', KEYS[1], 'count')) "
              + "if not start or not count or now >= start + window then "
              + "redis.call('HSET', KEYS[1], 'start', now, 'count', 1) "
              + "redis.call('PEXPIRE', KEYS[1], window) "
              + "return {1, 0} end "
              + "if count < limit then "
              + "redis.call('HINCRBY', KEYS[1], 'count', 1) "
              + "return {1, 0} end "
              + "return {0, math.max(1, math.ceil((start + window - now) / 1000))}",
          List.class);

  private final StringRedisTemplate redis;
  private final int limit;
  private final Duration window;
  private final String namespace;

  public RedisRateLimiter(StringRedisTemplate redis, String namespace, int limit, Duration window) {
    if (namespace == null || namespace.isBlank()) {
      throw new IllegalArgumentException("namespace must not be blank");
    }
    if (limit < 1) {
      throw new IllegalArgumentException("limit must be at least 1");
    }
    if (window.isZero() || window.isNegative()) {
      throw new IllegalArgumentException("window must be positive");
    }
    this.redis = redis;
    this.namespace = namespace;
    this.limit = limit;
    this.window = window;
  }

  @Override
  public Decision tryAcquire(String key, Instant now) {
    List<?> result =
        redis.execute(
            ACQUIRE,
            List.of(KEY_PREFIX + namespace + ":" + digest(key)),
            Long.toString(now.toEpochMilli()),
            Long.toString(Math.max(1, window.toMillis())),
            Integer.toString(limit));
    if (result == null || result.size() != 2) {
      throw new IllegalStateException("Redis returned an invalid rate limit result");
    }
    boolean allowed = Integer.parseInt(result.get(0).toString()) == 1;
    long retryAfterSeconds = Long.parseLong(result.get(1).toString());
    return allowed ? Decision.permit() : Decision.limited(retryAfterSeconds);
  }

  private static String digest(String value) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is unavailable", e);
    }
  }
}
