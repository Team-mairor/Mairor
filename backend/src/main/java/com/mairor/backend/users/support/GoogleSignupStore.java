package com.mairor.backend.users.support;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import tools.jackson.databind.json.JsonMapper;

/**
 * Google 로 처음 온 사용자의 가입 대기를 약관·추가 정보를 받을 때까지 보관하는 저장소. callback 이 검증한 Google 계정만 넣고, 회원은 가입 완료 때
 * 만든다(동의 없이 회원을 만들지 않는다). 키는 브라우저 임시 쿠키 값의 해시다.
 *
 * <p>운영 Redis 구현은 여러 API 인스턴스가 공유하고 만료 시 자동 삭제된다. 개발·테스트의 메모리 구현은 프로세스 안에서만 유효하다.
 */
public class GoogleSignupStore {

  private static final long DEFAULT_MAX_ENTRIES = 100_000;
  private static final String KEY_PREFIX = "mairor:auth:google:signup:";
  private static final JsonMapper JSON = JsonMapper.builder().build();
  private static final DefaultRedisScript<String> TAKE =
      new DefaultRedisScript<>(
          "local value = redis.call('GET', KEYS[1]) "
              + "if value then redis.call('DEL', KEYS[1]) end "
              + "return value",
          String.class);

  private record StoredPending(String subject, String email, String name, long expiresAtMillis) {}

  /**
   * 가입 대기.
   *
   * @param subject Google ID 토큰의 {@code sub}
   * @param email Google 이 확인한 이메일 (정규화한 값)
   * @param name Google 표시 이름. 없으면 {@code null}
   */
  public record Pending(String subject, String email, String name, Instant expiresAt) {

    /** {@code sub}·이메일이 로그에 남지 않도록 가린다. */
    @Override
    public String toString() {
      return "Pending[subject=***, email=***, expiresAt=" + expiresAt + "]";
    }
  }

  private final Duration ttl;
  private final Cache<String, Pending> entries;
  private final StringRedisTemplate redis;

  public GoogleSignupStore(Duration ttl) {
    this(ttl, DEFAULT_MAX_ENTRIES);
  }

  public GoogleSignupStore(Duration ttl, StringRedisTemplate redis) {
    this.ttl = ttl;
    this.entries = null;
    this.redis = redis;
  }

  GoogleSignupStore(Duration ttl, long maxEntries) {
    this.ttl = ttl;
    // Caffeine 만료는 메모리 정리용이다. 유효 여부는 저장한 만료 시각과 호출자가 넘긴 시각으로 판단한다
    this.entries = Caffeine.newBuilder().maximumSize(maxEntries).expireAfterWrite(ttl).build();
    this.redis = null;
  }

  /** 가입 대기를 보관하고 돌려준다. */
  public Pending save(String keyHash, String subject, String email, String name, Instant now) {
    Pending pending = new Pending(subject, email, name, now.plus(ttl));
    if (redis == null) {
      entries.put(keyHash, pending);
    } else {
      try {
        StoredPending stored =
            new StoredPending(subject, email, name, pending.expiresAt().toEpochMilli());
        redis
            .opsForValue()
            .set(
                KEY_PREFIX + keyHash,
                JSON.writeValueAsString(stored),
                Duration.ofMillis(Math.max(1, ttl.toMillis())));
      } catch (RuntimeException e) {
        throw new IllegalStateException("Could not serialize Google signup state", e);
      }
    }
    return pending;
  }

  /** 가입 대기를 읽는다. 지우지 않는다. 없거나 만료됐으면 비어 있다. */
  public Optional<Pending> find(String keyHash, Instant now) {
    Pending pending = redis == null ? entries.getIfPresent(keyHash) : read(keyHash);
    return Optional.ofNullable(pending).filter(p -> now.isBefore(p.expiresAt()));
  }

  /** 가입 대기를 꺼내고 지운다(가입 완료용, 1회). 없거나 만료됐으면 비어 있다. */
  public Optional<Pending> take(String keyHash, Instant now) {
    Pending pending;
    if (redis == null) {
      pending = entries.asMap().remove(keyHash);
    } else {
      String json = redis.execute(TAKE, List.of(KEY_PREFIX + keyHash));
      pending = decode(json);
    }
    return Optional.ofNullable(pending).filter(p -> now.isBefore(p.expiresAt()));
  }

  private Pending read(String keyHash) {
    return decode(redis.opsForValue().get(KEY_PREFIX + keyHash));
  }

  private static Pending decode(String json) {
    if (json == null) {
      return null;
    }
    try {
      StoredPending stored = JSON.readValue(json, StoredPending.class);
      return new Pending(
          stored.subject(),
          stored.email(),
          stored.name(),
          Instant.ofEpochMilli(stored.expiresAtMillis()));
    } catch (RuntimeException e) {
      throw new IllegalStateException("Could not deserialize Google signup state", e);
    }
  }
}
