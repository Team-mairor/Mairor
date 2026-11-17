package com.mairor.backend.users.support;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

/** Redis-backed temporary state for signup email verification or password reset. */
public class RedisEmailVerificationStore implements EmailVerificationStore {

  private static final DefaultRedisScript<List> RESERVE_SEND =
      new DefaultRedisScript<>(
          "local now=tonumber(ARGV[1]); local cooldown=tonumber(ARGV[2]); "
              + "local limit=tonumber(ARGV[3]); local window=3600000; "
              + "redis.call('ZREMRANGEBYSCORE',KEYS[2],'-inf',now-window); "
              + "local count=redis.call('ZCARD',KEYS[2]); "
              + "if count>=limit then local first=redis.call('ZRANGE',KEYS[2],0,0,'WITHSCORES'); "
              + "local retry=math.max(1,math.ceil((tonumber(first[2])+window-now)/1000)); "
              + "return {'HOURLY_LIMIT',tostring(retry),'0'} end; "
              + "local last=redis.call('ZREVRANGE',KEYS[2],0,0,'WITHSCORES'); "
              + "if #last>0 then local free=tonumber(last[2])+cooldown; if now<free then "
              + "return {'COOLDOWN',tostring(math.max(1,math.ceil((free-now)/1000))),'0'} end end; "
              + "local gen=redis.call('INCR',KEYS[3]); redis.call('ZADD',KEYS[2],now,tostring(gen)); "
              + "redis.call('PEXPIRE',KEYS[2],7200000); redis.call('PEXPIRE',KEYS[1],7200000); "
              + "return {'ALLOWED','0',tostring(gen)}",
          List.class);

  private static final DefaultRedisScript<Long> SAVE_CODE =
      new DefaultRedisScript<>(
          "if redis.call('HGET',KEYS[1],'generation') and "
              + "tonumber(redis.call('HGET',KEYS[1],'generation'))>tonumber(ARGV[3]) then return 0 end; "
              + "redis.call('HSET',KEYS[1],'generation',ARGV[3],'codeHash',ARGV[1],"
              + "'codeExpiresAt',ARGV[2],'attempts',0); redis.call('PEXPIRE',KEYS[1],7200000); return 1",
          Long.class);

  private static final DefaultRedisScript<Long> CANCEL_SEND =
      new DefaultRedisScript<>(
          "redis.call('ZREM',KEYS[2],ARGV[1]); if redis.call('HGET',KEYS[1],'generation')==ARGV[1] then "
              + "redis.call('HDEL',KEYS[1],'codeHash','codeExpiresAt','attempts') end; return 1",
          Long.class);

  private static final DefaultRedisScript<String> CONFIRM_CODE =
      new DefaultRedisScript<>(
          "local hash=redis.call('HGET',KEYS[1],'codeHash'); "
              + "local expiry=tonumber(redis.call('HGET',KEYS[1],'codeExpiresAt') or '0'); "
              + "if not hash or tonumber(ARGV[1])>=expiry then "
              + "redis.call('HDEL',KEYS[1],'codeHash','codeExpiresAt','attempts'); return 'EXPIRED_OR_MISSING' end; "
              + "local attempts=tonumber(redis.call('HGET',KEYS[1],'attempts') or '0'); "
              + "if attempts>=tonumber(ARGV[3]) then return 'ATTEMPTS_EXCEEDED' end; "
              + "if hash==ARGV[2] then redis.call('HDEL',KEYS[1],'codeHash','codeExpiresAt','attempts'); "
              + "return 'OK' end; redis.call('HINCRBY',KEYS[1],'attempts',1); return 'MISMATCH'",
          String.class);

  private static final DefaultRedisScript<Long> SAVE_TOKEN =
      new DefaultRedisScript<>(
          "local old=redis.call('GET',KEYS[2]); if old and old~=ARGV[1] then redis.call('DEL',ARGV[5]..old) end; "
              + "redis.call('HSET',KEYS[1],'email',ARGV[2],'stamp',ARGV[3],"
              + "'expiresAt',ARGV[4],'emailIndexKey',ARGV[7]); "
              + "redis.call('PEXPIRE',KEYS[1],ARGV[6]); redis.call('SET',KEYS[2],ARGV[1],'PX',ARGV[6]); return 1",
          Long.class);

  private static final DefaultRedisScript<Long> DELETE_TOKEN =
      new DefaultRedisScript<>(
          "local email=redis.call('HGET',KEYS[1],'email'); redis.call('DEL',KEYS[1]); "
              + "if email and redis.call('GET',KEYS[2])==ARGV[1] then redis.call('DEL',KEYS[2]) end; return 1",
          Long.class);

  private static final DefaultRedisScript<List> FIND_TOKEN =
      new DefaultRedisScript<>(
          "if redis.call('GET',KEYS[2])~=ARGV[1] then return nil end; "
              + "local email=redis.call('HGET',KEYS[1],'email'); "
              + "local stamp=redis.call('HGET',KEYS[1],'stamp'); "
              + "local expiry=tonumber(redis.call('HGET',KEYS[1],'expiresAt') or '0'); "
              + "if not email or not stamp or tonumber(ARGV[2])>=expiry then return nil end; "
              + "return {email,stamp}",
          List.class);

  private static final DefaultRedisScript<Long> INVALIDATE_EMAIL =
      new DefaultRedisScript<>(
          "local old=redis.call('GET',KEYS[2]); if old then redis.call('DEL',ARGV[1]..old) end; "
              + "redis.call('DEL',KEYS[2]); redis.call('HDEL',KEYS[1],'codeHash','codeExpiresAt','attempts'); return 1",
          Long.class);

  private final StringRedisTemplate redis;
  private final Clock clock;
  private final String prefix;
  private final Duration resendCooldown;
  private final int hourlyLimit;

  public RedisEmailVerificationStore(
      StringRedisTemplate redis,
      Clock clock,
      String namespace,
      Duration resendCooldown,
      int hourlyLimit) {
    if (namespace == null || namespace.isBlank()) {
      throw new IllegalArgumentException("namespace must not be blank");
    }
    if (resendCooldown.isNegative() || hourlyLimit < 1) {
      throw new IllegalArgumentException("resendCooldown and hourlyLimit are invalid");
    }
    this.redis = redis;
    this.clock = clock;
    this.prefix = "mairor:verification:" + namespace + ":";
    this.resendCooldown = resendCooldown;
    this.hourlyLimit = hourlyLimit;
  }

  @Override
  public SendPermit reserveSend(String email, Instant now) {
    List<?> result =
        redis.execute(
            RESERVE_SEND,
            List.of(stateKey(email), sendsKey(email), prefix + "generation"),
            Long.toString(now.toEpochMilli()),
            Long.toString(resendCooldown.toMillis()),
            Integer.toString(hourlyLimit));
    if (result == null || result.size() != 3) {
      throw new IllegalStateException("Redis returned an invalid send reservation result");
    }
    SendPermit.Status status = SendPermit.Status.valueOf(result.get(0).toString());
    long retry = Long.parseLong(result.get(1).toString());
    long generation = Long.parseLong(result.get(2).toString());
    return status == SendPermit.Status.ALLOWED
        ? SendPermit.allowed(generation)
        : SendPermit.blocked(status, retry);
  }

  @Override
  public void saveCode(String email, String codeHash, Instant expiresAt, long generation) {
    redis.execute(
        SAVE_CODE,
        List.of(stateKey(email)),
        codeHash,
        Long.toString(expiresAt.toEpochMilli()),
        Long.toString(generation));
  }

  @Override
  public void cancelSend(String email, long generation) {
    redis.execute(
        CANCEL_SEND, List.of(stateKey(email), sendsKey(email)), Long.toString(generation));
  }

  @Override
  public ConfirmOutcome confirmCode(String email, String codeHash, Instant now, int maxAttempts) {
    String result =
        redis.execute(
            CONFIRM_CODE,
            List.of(stateKey(email)),
            Long.toString(now.toEpochMilli()),
            codeHash,
            Integer.toString(maxAttempts));
    return result == null ? ConfirmOutcome.EXPIRED_OR_MISSING : ConfirmOutcome.valueOf(result);
  }

  @Override
  public void saveToken(String tokenHash, String email, long stamp, Instant expiresAt) {
    long ttl = Duration.between(clock.instant(), expiresAt).toMillis();
    if (ttl <= 0) {
      deleteToken(tokenHash);
      return;
    }
    String tokenKey = tokenKey(tokenHash);
    redis.execute(
        SAVE_TOKEN,
        List.of(tokenKey, emailTokenKey(email)),
        tokenHash,
        email,
        Long.toString(stamp),
        Long.toString(expiresAt.toEpochMilli()),
        prefix + "token:",
        Long.toString(ttl),
        emailTokenKey(email));
  }

  @Override
  public boolean hasValidToken(String tokenHash, String email, Instant now) {
    return findToken(tokenHash, now).filter(value -> value.email().equals(email)).isPresent();
  }

  @Override
  public Optional<IssuedToken> findToken(String tokenHash, Instant now) {
    String tokenKey = tokenKey(tokenHash);
    Object emailIndexKey = redis.opsForHash().get(tokenKey, "emailIndexKey");
    if (emailIndexKey == null) {
      return Optional.empty();
    }
    List<?> result =
        redis.execute(
            FIND_TOKEN,
            List.of(tokenKey, emailIndexKey.toString()),
            tokenHash,
            Long.toString(now.toEpochMilli()));
    if (result == null || result.size() != 2) {
      return Optional.empty();
    }
    return Optional.of(
        new IssuedToken(result.get(0).toString(), Long.parseLong(result.get(1).toString())));
  }

  @Override
  public void deleteToken(String tokenHash) {
    String key = tokenKey(tokenHash);
    Object email = redis.opsForHash().get(key, "email");
    if (email == null) {
      redis.delete(key);
      return;
    }
    redis.execute(DELETE_TOKEN, List.of(key, emailTokenKey(email.toString())), tokenHash);
  }

  @Override
  public void invalidateAll(String email) {
    redis.execute(
        INVALIDATE_EMAIL, List.of(stateKey(email), emailTokenKey(email)), prefix + "token:");
  }

  private String stateKey(String email) {
    return prefix + "state:" + digest(email);
  }

  private String sendsKey(String email) {
    return prefix + "sends:" + digest(email);
  }

  private String emailTokenKey(String email) {
    return prefix + "token-email:" + digest(email);
  }

  private String tokenKey(String tokenHash) {
    return prefix + "token:" + tokenHash;
  }

  private static String digest(String value) {
    try {
      return HexFormat.of()
          .formatHex(
              MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 is not available", e);
    }
  }
}
