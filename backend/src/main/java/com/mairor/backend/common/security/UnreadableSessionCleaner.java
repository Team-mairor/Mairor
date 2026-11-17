package com.mairor.backend.common.security;

import java.util.List;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.data.redis.RedisIndexedSessionRepository;
import org.springframework.stereotype.Component;

/**
 * 값을 읽을 수 없는(손상된) 세션을 세션 값을 읽지 않고 지운다.
 *
 * <p>Spring Session 은 세션을 지울 때도 먼저 세션 값을 읽는다. 그래서 손상된 세션은 저장소의 기본 삭제로 지울 수 없고, 회원 색인으로 세션을 찾는 조회도 그
 * 세션 때문에 통째로 실패한다. 이대로 두면 그 회원은 새 로그인(이전 세션 대체)이나 비밀번호 재설정(모든 세션 종료)을 끝낼 수 없다. 이 클래스는 회원 색인에서 세션 ID
 * 만 읽고, 세션 해시·만료 알림 키·색인 항목을 직접 지운다.
 */
@Component
public class UnreadableSessionCleaner {

  private final RedisOperations<String, Object> redis;
  private final String namespace;

  public UnreadableSessionCleaner(
      RedisIndexedSessionRepository repository,
      @Value("${spring.session.data.redis.namespace:spring:session}") String namespace) {
    this.redis = repository.getSessionRedisOperations();
    this.namespace = namespace;
  }

  /** 회원 색인에 올라 있는 세션 ID. 세션 값은 읽지 않는다. */
  public List<String> sessionIdsOf(String principalName) {
    Set<Object> members = redis.opsForSet().members(indexKey(principalName));
    if (members == null) {
      return List.of();
    }
    return members.stream().map(String::valueOf).toList();
  }

  /** 세션 값을 읽지 않고 세션과 그 색인 항목을 지운다. */
  public void remove(String principalName, String sessionId) {
    redis.delete(List.of(sessionKey(sessionId), namespace + ":sessions:expires:" + sessionId));
    redis.opsForSet().remove(indexKey(principalName), sessionId);
  }

  /** 예외의 원인 중에 세션 값을 읽지 못한 실패가 있는지. */
  public static boolean isUnreadable(Throwable e) {
    for (Throwable t = e; t != null; t = t.getCause() == t ? null : t.getCause()) {
      if (t instanceof UnreadableSessionException) {
        return true;
      }
    }
    return false;
  }

  private String sessionKey(String sessionId) {
    return namespace + ":sessions:" + sessionId;
  }

  private String indexKey(String principalName) {
    return namespace
        + ":index:"
        + FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME
        + ":"
        + principalName;
  }
}
