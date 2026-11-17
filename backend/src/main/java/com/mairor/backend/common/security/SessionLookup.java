package com.mairor.backend.common.security;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Component;

/**
 * 손상된 세션이 섞여 있어도 끝까지 동작하는 세션 조회·삭제.
 *
 * <p>Spring Session 은 회원 색인으로 세션을 찾을 때 그 회원의 세션 값을 모두 읽는다. 값을 읽을 수 없는 세션이 하나라도 있으면 조회가 통째로 실패하고, 그
 * 세션은 기본 삭제로도 지울 수 없다. 여기서는 그런 경우에만 {@link UnreadableSessionCleaner} 로 세션 ID 를 따로 읽어 하나씩 확인하고, 읽을 수
 * 없는 세션은 값을 읽지 않고 지운다. 그 밖의 저장소 오류는 그대로 던진다.
 */
@Component
public class SessionLookup {

  private final FindByIndexNameSessionRepository<? extends Session> sessions;
  private final UnreadableSessionCleaner unreadable;

  public SessionLookup(
      FindByIndexNameSessionRepository<? extends Session> sessions,
      UnreadableSessionCleaner unreadable) {
    this.sessions = sessions;
    this.unreadable = unreadable;
  }

  /** 회원의 세션. 값을 읽을 수 없는 세션은 ID 만 있고 값이 {@code null} 이다. */
  public Map<String, Session> byPrincipal(String principalName) {
    try {
      return new LinkedHashMap<String, Session>(sessions.findByPrincipalName(principalName));
    } catch (RuntimeException e) {
      rethrowUnlessUnreadable(e);
    }
    Map<String, Session> found = new LinkedHashMap<>();
    for (String id : unreadable.sessionIdsOf(principalName)) {
      try {
        Session session = sessions.findById(id);
        if (session != null) {
          found.put(id, session);
        }
      } catch (RuntimeException e) {
        rethrowUnlessUnreadable(e);
        found.put(id, null);
      }
    }
    return found;
  }

  /** 만료되지 않고 값을 읽을 수 있는 세션이 있는지. 손상된 세션은 다시 쓸 수 없으므로 없는 것으로 본다. */
  public boolean isUsable(String sessionId) {
    try {
      Session session = sessions.findById(sessionId);
      return session != null && !session.isExpired();
    } catch (RuntimeException e) {
      rethrowUnlessUnreadable(e);
      return false;
    }
  }

  /** 세션을 지운다. 값을 읽을 수 없는 세션은 값을 읽지 않고 지운다. */
  public void delete(String principalName, String sessionId) {
    try {
      sessions.deleteById(sessionId);
    } catch (RuntimeException e) {
      rethrowUnlessUnreadable(e);
      unreadable.remove(principalName, sessionId);
    }
  }

  private static void rethrowUnlessUnreadable(RuntimeException e) {
    if (!UnreadableSessionCleaner.isUnreadable(e)) {
      throw e;
    }
  }
}
