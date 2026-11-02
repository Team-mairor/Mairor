package com.mairor.backend.users.support;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

/**
 * Google 로 처음 온 사용자의 가입 대기를 약관·추가 정보를 받을 때까지 보관하는 인메모리 저장소. callback 이 검증한 Google 계정만 넣고, 회원은 가입 완료
 * 때 만든다(동의 없이 회원을 만들지 않는다). 키는 브라우저 임시 쿠키 값의 해시다.
 *
 * <p>한계: 서버 1대에서만 정확하고, 재시작하면 가입 대기가 사라진다(사용자는 Google 로 다시 시작). 크기 제한을 넘으면 Caffeine 이 정한 항목이 퇴거된다.
 */
public class GoogleSignupStore {

  private static final long DEFAULT_MAX_ENTRIES = 100_000;

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

  public GoogleSignupStore(Duration ttl) {
    this(ttl, DEFAULT_MAX_ENTRIES);
  }

  GoogleSignupStore(Duration ttl, long maxEntries) {
    this.ttl = ttl;
    // Caffeine 만료는 메모리 정리용이다. 유효 여부는 저장한 만료 시각과 호출자가 넘긴 시각으로 판단한다
    this.entries = Caffeine.newBuilder().maximumSize(maxEntries).expireAfterWrite(ttl).build();
  }

  /** 가입 대기를 보관하고 돌려준다. */
  public Pending save(String keyHash, String subject, String email, String name, Instant now) {
    Pending pending = new Pending(subject, email, name, now.plus(ttl));
    entries.put(keyHash, pending);
    return pending;
  }

  /** 가입 대기를 읽는다. 지우지 않는다. 없거나 만료됐으면 비어 있다. */
  public Optional<Pending> find(String keyHash, Instant now) {
    return Optional.ofNullable(entries.getIfPresent(keyHash))
        .filter(p -> now.isBefore(p.expiresAt()));
  }

  /** 가입 대기를 꺼내고 지운다(가입 완료용, 1회). 없거나 만료됐으면 비어 있다. */
  public Optional<Pending> take(String keyHash, Instant now) {
    return Optional.ofNullable(entries.asMap().remove(keyHash))
        .filter(p -> now.isBefore(p.expiresAt()));
  }
}
