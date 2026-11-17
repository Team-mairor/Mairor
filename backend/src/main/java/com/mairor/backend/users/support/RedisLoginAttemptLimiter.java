package com.mairor.backend.users.support;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

/**
 * Redis 에 두는 로그인 시도 제한. 이메일 하나의 상태 변화는 Lua 스크립트 하나로 처리해 서버 여러 대에서도 원자적이다.
 *
 * <p>인메모리 구현과 다른 점이 하나 있다. 진행 중인 시도가 남은 상태도 마지막 시도 뒤 {@code attempt-ttl} 이 지나면 지운다. 시도 도중에 서버가 죽으면
 * 그 시도는 끝나지 않는데, 인메모리는 재시작하면 상태가 사라지지만 Redis 에서는 영영 남아 그 이메일이 계속 막힌다. 요청은 그보다 훨씬 먼저 끝나므로 정상 시도를 지울
 * 일은 없다.
 */
public class RedisLoginAttemptLimiter implements LoginAttemptLimiter {

  private static final String STATE_PREFIX = "mairor:auth:login-attempt:state:";
  private static final String INDEX_KEY = "mairor:auth:login-attempt:index";
  private static final DefaultRedisScript<List> ACQUIRE =
      new DefaultRedisScript<>(
          "local now = tonumber(ARGV[1]) "
              + "local ttl = tonumber(ARGV[2]) "
              + "local maxFailures = tonumber(ARGV[3]) "
              + "local maxEntries = tonumber(ARGV[4]) "
              + "local candidateEpoch = ARGV[5] "
              + "local statePrefix = ARGV[6] "
              + "local member = ARGV[7] "
              + "local expired = redis.call('ZRANGEBYSCORE', KEYS[2], '-inf', now, 'LIMIT', 0, 1000) "
              + "for _, oldMember in ipairs(expired) do "
              + "redis.call('DEL', statePrefix .. oldMember) "
              + "redis.call('ZREM', KEYS[2], oldMember) end "
              + "local state = KEYS[1] "
              + "local lockedUntil = tonumber(redis.call('HGET', state, 'lockedUntil') or '0') "
              + "if lockedUntil > now then "
              + "return {1, math.max(1, math.ceil((lockedUntil - now) / 1000))} end "
              + "if lockedUntil > 0 then redis.call('DEL', state) redis.call('ZREM', KEYS[2], member) end "
              + "if redis.call('EXISTS', state) == 0 then "
              + "if redis.call('ZCARD', KEYS[2]) >= maxEntries then "
              + "local all = redis.call('ZRANGE', KEYS[2], 0, -1) "
              + "local removed = false "
              + "local earliestUnlock = nil "
              + "for _, oldMember in ipairs(all) do "
              + "local oldState = statePrefix .. oldMember "
              + "local oldFlight = tonumber(redis.call('HGET', oldState, 'inFlight') or '0') "
              + "local oldLock = tonumber(redis.call('HGET', oldState, 'lockedUntil') or '0') "
              + "if oldFlight == 0 and oldLock == 0 then "
              + "redis.call('DEL', oldState) redis.call('ZREM', KEYS[2], oldMember) removed = true break end "
              + "if oldLock > now and (earliestUnlock == nil or oldLock < earliestUnlock) then "
              + "earliestUnlock = oldLock end end "
              + "if not removed then "
              + "if earliestUnlock == nil then return {3, 1} end "
              + "return {3, math.max(1, math.ceil((earliestUnlock - now) / 1000))} end end "
              + "redis.call('HSET', state, 'epoch', candidateEpoch, 'failures', 0, 'inFlight', 0, 'lastAttempt', now, 'lockedUntil', 0) "
              + "redis.call('ZADD', KEYS[2], now + ttl, member) end "
              + "local failures = tonumber(redis.call('HGET', state, 'failures') or '0') "
              + "local inFlight = tonumber(redis.call('HGET', state, 'inFlight') or '0') "
              + "if failures + inFlight >= maxFailures then return {2, 1} end "
              + "inFlight = redis.call('HINCRBY', state, 'inFlight', 1) "
              + "redis.call('HSET', state, 'lastAttempt', now) "
              + "redis.call('ZADD', KEYS[2], now + ttl, member) "
              + "return {0, redis.call('HGET', state, 'epoch')}",
          List.class);

  private static final DefaultRedisScript<Long> FINISH =
      new DefaultRedisScript<>(
          "local state = KEYS[1] "
              + "if redis.call('HGET', state, 'epoch') ~= ARGV[1] then return 0 end "
              + "local inFlight = tonumber(redis.call('HGET', state, 'inFlight') or '0') "
              + "if inFlight > 0 then inFlight = redis.call('HINCRBY', state, 'inFlight', -1) end "
              + "local operation = ARGV[2] "
              + "if operation == 'success' then redis.call('HSET', state, 'failures', 0) "
              + "elseif operation == 'fail' then "
              + "local failures = redis.call('HINCRBY', state, 'failures', 1) "
              + "redis.call('HSET', state, 'lastAttempt', ARGV[3]) "
              + "if failures >= tonumber(ARGV[4]) then "
              + "local untilTime = tonumber(ARGV[3]) + tonumber(ARGV[5]) "
              + "redis.call('HSET', state, 'lockedUntil', untilTime, 'inFlight', 0) "
              + "redis.call('ZADD', KEYS[2], untilTime, ARGV[6]) return 1 end end "
              + "local failures = tonumber(redis.call('HGET', state, 'failures') or '0') "
              + "local lockedUntil = tonumber(redis.call('HGET', state, 'lockedUntil') or '0') "
              + "if inFlight == 0 and failures == 0 then "
              + "redis.call('DEL', state) redis.call('ZREM', KEYS[2], ARGV[6]) "
              + "else local lastAttempt = tonumber(redis.call('HGET', state, 'lastAttempt') or ARGV[3]) "
              + "local score = lastAttempt + tonumber(ARGV[7]) "
              + "if lockedUntil > 0 then score = lockedUntil end "
              + "redis.call('ZADD', KEYS[2], score, ARGV[6]) end "
              + "return 1",
          Long.class);

  private static final DefaultRedisScript<Long> RESET =
      new DefaultRedisScript<>(
          "local state = KEYS[1] "
              + "if redis.call('EXISTS', state) == 0 then return 0 end "
              + "local inFlight = tonumber(redis.call('HGET', state, 'inFlight') or '0') "
              + "if inFlight == 0 then redis.call('DEL', state) redis.call('ZREM', KEYS[2], ARGV[1]) "
              + "else redis.call('HSET', state, 'failures', 0, 'lockedUntil', 0) "
              + "local lastAttempt = tonumber(redis.call('HGET', state, 'lastAttempt') or '0') "
              + "redis.call('ZADD', KEYS[2], lastAttempt + tonumber(ARGV[2]), ARGV[1]) end "
              + "return 1",
          Long.class);

  private final StringRedisTemplate redis;
  private final LoginProperties properties;

  public RedisLoginAttemptLimiter(StringRedisTemplate redis, LoginProperties properties) {
    this.redis = redis;
    this.properties = properties;
  }

  @Override
  public Result tryAcquire(String email, Instant now) {
    String member = emailHash(email);
    List<?> result =
        redis.execute(
            ACQUIRE,
            List.of(STATE_PREFIX + member, INDEX_KEY),
            Long.toString(now.toEpochMilli()),
            Long.toString(durationMillis(properties.attemptTtl())),
            Integer.toString(properties.maxFailures()),
            Integer.toString(properties.maxEntries()),
            Long.toString(ThreadLocalRandom.current().nextLong(1, Long.MAX_VALUE)),
            STATE_PREFIX,
            member);
    if (result == null || result.size() < 2) {
      throw new IllegalStateException("Redis returned an invalid login attempt result");
    }
    int status = Integer.parseInt(result.get(0).toString());
    long value = Long.parseLong(result.get(1).toString());
    return switch (status) {
      case 0 -> new Allowed(new Ticket(email, value));
      case 1 -> new Locked(value);
      case 2 -> new Pending(value);
      case 3 -> new Saturated(value);
      default -> throw new IllegalStateException("Redis returned an unknown login attempt status");
    };
  }

  @Override
  public void succeed(Ticket ticket) {
    finish(ticket, "success", Instant.now());
  }

  @Override
  public void fail(Ticket ticket, Instant now) {
    finish(ticket, "fail", now);
  }

  @Override
  public void refund(Ticket ticket) {
    finish(ticket, "refund", Instant.now());
  }

  private void finish(Ticket ticket, String operation, Instant now) {
    if (!ticket.close()) {
      return;
    }
    String member = emailHash(ticket.email());
    redis.execute(
        FINISH,
        List.of(STATE_PREFIX + member, INDEX_KEY),
        Long.toString(ticket.epoch()),
        operation,
        Long.toString(now.toEpochMilli()),
        Integer.toString(properties.maxFailures()),
        Long.toString(durationMillis(properties.lockDuration())),
        member,
        Long.toString(durationMillis(properties.attemptTtl())));
  }

  @Override
  public void reset(String email) {
    String member = emailHash(email);
    redis.execute(
        RESET,
        List.of(STATE_PREFIX + member, INDEX_KEY),
        member,
        Long.toString(durationMillis(properties.attemptTtl())));
  }

  private static long durationMillis(java.time.Duration duration) {
    return Math.max(1, duration.toMillis());
  }

  private static String emailHash(String email) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(email.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is unavailable", e);
    }
  }
}
