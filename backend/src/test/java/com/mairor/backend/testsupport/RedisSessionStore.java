package com.mairor.backend.testsupport;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.data.redis.RedisIndexedSessionRepository;
import org.springframework.stereotype.Component;

/**
 * 테스트가 Redis 세션 저장소를 직접 보고 고친다. 세션 하나는 {@code <namespace>:sessions:<id>} 해시이고, 마지막 접근 시각 ({@code
 * lastAccessedTime}, 밀리초)과 유휴 만료({@code maxInactiveInterval}, 초)를 필드로 둔다. Spring Session 은 읽을 때 둘을
 * 더해 만료를 판정하므로 마지막 접근 시각만 과거로 옮기면 그만큼 요청이 없었던 상태가 된다.
 *
 * <p>Spring Session 은 세션을 지울 때 해시를 바로 없애지 않고 유휴 만료를 0 으로 바꿔 5분 뒤에 사라지게 둔다(만료 알림에 값을 실어 보내려고). 그래서 이
 * 클래스는 유휴 만료가 0 인 해시를 "지워진 세션"으로 본다.
 */
@Component
public class RedisSessionStore {

  private static final String LAST_ACCESSED = "lastAccessedTime";
  private static final String MAX_INACTIVE = "maxInactiveInterval";

  private final RedisOperations<String, Object> redis;
  private final String sessionsPrefix;
  private final String namespace;

  public RedisSessionStore(
      RedisIndexedSessionRepository repository,
      @Value("${spring.session.data.redis.namespace:spring:session}") String namespace) {
    this.redis = repository.getSessionRedisOperations();
    this.namespace = namespace;
    this.sessionsPrefix = namespace + ":sessions:";
  }

  /** 세션 저장소의 키를 모두 지운다. */
  public void clear() {
    Set<String> keys = redis.keys(namespace + ":*");
    if (keys != null && !keys.isEmpty()) {
      redis.delete(keys);
    }
  }

  /** 지워지지 않은 세션 수. 만료 알림용 보조 키는 세지 않는다. */
  public long count() {
    Set<String> keys = redis.keys(sessionsPrefix + "*");
    if (keys == null) {
      return 0;
    }
    return keys.stream()
        .filter(key -> !key.startsWith(sessionsPrefix + "expires:"))
        .filter(this::live)
        .count();
  }

  /** 로그인한 회원 색인에 올라 있는 회원 ID(principal name). */
  public List<String> indexedPrincipals() {
    String prefix =
        namespace + ":index:" + FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME + ":";
    Set<String> keys = redis.keys(prefix + "*");
    if (keys == null) {
      return List.of();
    }
    return keys.stream().map(key -> key.substring(prefix.length())).toList();
  }

  /** 지워지지 않은 세션이 있는지. */
  public boolean exists(String sessionId) {
    return live(key(sessionId));
  }

  private boolean live(String key) {
    Object maxInactive = redis.opsForHash().get(key, MAX_INACTIVE);
    return maxInactive instanceof Number seconds && seconds.longValue() > 0;
  }

  /** 마지막 접근 시각을 {@code elapsed} 만큼 과거로 되돌려, 그만큼 요청이 없었던 상태를 만든다. */
  public void idleFor(String sessionId, Duration elapsed) {
    long lastAccessed = lastAccessedMillis(sessionId);
    redis.opsForHash().put(key(sessionId), LAST_ACCESSED, lastAccessed - elapsed.toMillis());
  }

  /**
   * Redis 가 이 세션의 만료 알림 키를 지금 만료시키게 한다. 운영에서 유휴 만료가 일어날 때와 같은 경로(키 만료 알림 → {@code
   * SessionExpiredEvent})로 종료 훅이 불린다. 알림은 비동기라 결과는 기다려서 확인한다.
   */
  public void expireNow(String sessionId) {
    redis.expire(sessionsPrefix + "expires:" + sessionId, Duration.ofMillis(1));
  }

  /** 서버 유휴 만료 시각(밀리초). 마지막 접근 시각 + 유휴 만료. */
  public long expiryMillis(String sessionId) {
    Object maxInactive = redis.opsForHash().get(key(sessionId), MAX_INACTIVE);
    return lastAccessedMillis(sessionId) + ((Number) maxInactive).longValue() * 1000;
  }

  /** 세션 속성 하나를 읽을 수 없는 바이트로 바꾼다. */
  public void corruptAttribute(String sessionId, String attributeName) {
    byte[] key = key(sessionId).getBytes(StandardCharsets.UTF_8);
    byte[] field = ("sessionAttr:" + attributeName).getBytes(StandardCharsets.UTF_8);
    redis.execute(
        (RedisCallback<Object>)
            connection -> connection.hashCommands().hSet(key, field, new byte[] {0}));
  }

  private long lastAccessedMillis(String sessionId) {
    Object value = redis.opsForHash().get(key(sessionId), LAST_ACCESSED);
    if (value == null) {
      throw new IllegalStateException("세션이 없습니다: " + sessionId);
    }
    return ((Number) value).longValue();
  }

  private String key(String sessionId) {
    return sessionsPrefix + sessionId;
  }
}
