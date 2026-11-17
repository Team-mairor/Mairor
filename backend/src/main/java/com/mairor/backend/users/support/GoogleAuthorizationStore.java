package com.mairor.backend.users.support;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

/**
 * 진행 중인 Google 로그인(state·nonce·PKCE verifier 가 든 인가 요청)을 callback 때까지 보관하는 저장소. 키는 브라우저 임시 쿠키 값의
 * 해시라서 저장소 내용만으로는 쿠키를 만들 수 없다. 꺼내면 지워지므로 한 번만 쓸 수 있다.
 *
 * <p>세션에 두지 않는 이유: 서비스 세션 쿠키가 {@code SameSite=Strict} 라 Google 에서 돌아오는 요청에 붙지 않고, 로그인 시작만으로 세션 행을
 * 만들지 않기 위해서다.
 *
 * <p>운영 Redis 구현은 여러 API 인스턴스가 공유하고 만료 시 자동 삭제된다. 개발·테스트의 메모리 구현은 프로세스 안에서만 유효하다.
 */
public class GoogleAuthorizationStore {

  private static final long DEFAULT_MAX_ENTRIES = 100_000;
  private static final String KEY_PREFIX = "mairor:auth:google:authorization:";
  private static final DefaultRedisScript<String> TAKE =
      new DefaultRedisScript<>(
          "local value = redis.call('GET', KEYS[1]) "
              + "if value then redis.call('DEL', KEYS[1]) end "
              + "return value",
          String.class);

  private record Entry(OAuth2AuthorizationRequest request, Instant expiresAt) {}

  private final Duration ttl;
  private final Cache<String, Entry> entries;
  private final StringRedisTemplate redis;

  public GoogleAuthorizationStore(Duration ttl) {
    this(ttl, DEFAULT_MAX_ENTRIES);
  }

  public GoogleAuthorizationStore(Duration ttl, StringRedisTemplate redis) {
    this.ttl = ttl;
    this.entries = null;
    this.redis = redis;
  }

  GoogleAuthorizationStore(Duration ttl, long maxEntries) {
    this.ttl = ttl;
    // Caffeine 만료는 메모리 정리용이다. 유효 여부는 저장한 만료 시각과 호출자가 넘긴 시각으로 판단한다
    this.entries = Caffeine.newBuilder().maximumSize(maxEntries).expireAfterWrite(ttl).build();
    this.redis = null;
  }

  /** 인가 요청을 보관하고 만료 시각을 돌려준다. */
  public Instant save(String keyHash, OAuth2AuthorizationRequest request, Instant now) {
    Instant expiresAt = now.plus(ttl);
    if (redis == null) {
      entries.put(keyHash, new Entry(request, expiresAt));
    } else {
      redis
          .opsForValue()
          .set(
              KEY_PREFIX + keyHash,
              OAuth2AuthorizationRequestCodec.encode(request, expiresAt),
              Duration.ofMillis(Math.max(1, ttl.toMillis())));
    }
    return expiresAt;
  }

  /** 인가 요청을 꺼내고 지운다. 없거나 만료됐으면 비어 있다. */
  public Optional<OAuth2AuthorizationRequest> take(String keyHash, Instant now) {
    if (redis == null) {
      Entry entry = entries.asMap().remove(keyHash);
      if (entry == null || !now.isBefore(entry.expiresAt())) {
        return Optional.empty();
      }
      return Optional.of(entry.request());
    }
    String json = redis.execute(TAKE, List.of(KEY_PREFIX + keyHash));
    if (json == null) {
      return Optional.empty();
    }
    OAuth2AuthorizationRequestCodec.Decoded decoded = OAuth2AuthorizationRequestCodec.decode(json);
    return now.isBefore(decoded.expiresAt()) ? Optional.of(decoded.request()) : Optional.empty();
  }
}
