package com.mairor.backend.users.service;

import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import com.mairor.backend.common.security.SessionEndNotifier;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.common.security.SessionLookup;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

/**
 * 회원의 로그인 세션 정리: 로그아웃 직전 훅, 새 로그인이 이전 세션을 대체, 비밀번호 재설정이 모든 세션을 끊음.
 *
 * <p>세션은 {@link SessionLookup} 으로 다룬다. Spring Session 이 {@code PRINCIPAL_NAME} 을 userId 로 색인하므로 회원의
 * 세션을 찾을 수 있다. 값을 읽을 수 없는(손상된) 세션도 찾아 지우므로, 손상된 세션 하나 때문에 그 회원이 다시 로그인하거나 비밀번호를 재설정하지 못하는 일은 없다.
 *
 * <p>보장 범위: 호출 시점에 조회된 세션을 지운다. 지우는 도중에 막 시작된 로그인이 나중에 발급한 세션이나 이미 인증을 통과해 실행 중인 요청은 막지 못한다.
 */
@Service
public class UserSessionService {

  private final SessionLookup sessions;
  private final SessionEndNotifier sessionEnd;

  public UserSessionService(SessionLookup sessions, SessionEndNotifier sessionEnd) {
    this.sessions = sessions;
    this.sessionEnd = sessionEnd;
  }

  /**
   * 로그아웃 직전의 정리. 세션을 끝내는 쪽({@code CurrentSessionEnder})을 부르기 <b>전에</b> 호출한다. 종료 훅이 실패하면 예외를 던지고,
   * 그러면 호출한 쪽이 세션을 끝내지 않으므로 회원은 세션이 남은 채 같은 요청을 다시 보낼 수 있다.
   */
  public void beforeLogout(UUID userId, String currentSessionId) {
    sessionEnd.strict(new SessionEnd(userId.toString(), currentSessionId, SessionEndReason.LOGOUT));
  }

  /**
   * 이 회원의 모든 세션을 끊는다(비밀번호 재설정). 유효하지 않거나 기기 정보가 없는 세션도 함께 지운다. 현재 세션({@code currentSessionId})은 다른
   * 세션을 모두 지운 뒤 마지막에 지운다. 요청이 들고 있는 현재 세션은 응답을 커밋할 때 되살아날 수 있으므로 호출자가 따로 끝내야 한다({@code
   * CurrentSessionEnder}).
   *
   * <p>세션마다 지우기 <b>전에</b> 종료 훅({@link SessionEndHook})을 호출한다. 훅이 실패한 세션은 지우지 않는다.
   *
   * <p><b>원자적이지 않다.</b> 세션은 하나씩 지운다. 도중에 정리하지 못한 세션(훅 또는 삭제 실패)이 있으면 나머지는 끝까지 시도하고, 현재 세션은 지우지 않은 채
   * 첫 번째 실패를 던진다(나머지 실패는 suppressed 로 붙는다). 현재 기기가 살아 있으므로 같은 요청을 다시 보내 마무리할 수 있다. 이미 끝난 세션은 다시
   * 조회되지 않아 훅이 다시 호출되지 않는다.
   *
   * @param currentSessionId 요청을 보낸 세션의 ID. 없거나 이 회원의 세션이 아니면 {@code null} 로 두거나 무시된다
   * @return 지운 세션 수
   */
  public int revokeAll(UUID userId, String currentSessionId) {
    List<String> others = new ArrayList<>();
    boolean hasCurrent = false;
    for (String id : sessions.byPrincipal(userId.toString()).keySet()) {
      if (id.equals(currentSessionId)) {
        hasCurrent = true;
      } else {
        others.add(id);
      }
    }

    int deleted = 0;
    RuntimeException failure = null;
    for (String id : others) {
      try {
        endForAll(userId, id);
        deleted++;
      } catch (RuntimeException e) {
        if (failure == null) {
          failure = e;
        } else {
          failure.addSuppressed(e);
        }
      }
    }
    if (failure != null) {
      throw failure;
    }
    if (hasCurrent) {
      endForAll(userId, currentSessionId);
      deleted++;
    }
    return deleted;
  }

  /** 현재 세션이 없는 호출(예: 비밀번호 재설정)을 위한 형태. 이 회원의 모든 세션을 지운다. */
  public int revokeAll(UUID userId) {
    return revokeAll(userId, null);
  }

  /** 새 로그인을 만들기 전에 이 회원의 기존 로그인 세션을 모두 끝낸다(계정당 로그인 세션 1개). 이미 만료된 세션은 훅 없이 넘어간다. */
  public int replaceForNewLogin(UUID userId) {
    int deleted = 0;
    RuntimeException failure = null;
    for (Map.Entry<String, Session> entry : sessions.byPrincipal(userId.toString()).entrySet()) {
      Session session = entry.getValue();
      if (session != null && session.isExpired()) {
        continue;
      }
      try {
        sessionEnd.bestEffort(
            new SessionEnd(userId.toString(), entry.getKey(), SessionEndReason.REPLACED_BY_LOGIN));
        sessions.delete(userId.toString(), entry.getKey());
        deleted++;
      } catch (RuntimeException e) {
        if (failure == null) {
          failure = e;
        } else {
          failure.addSuppressed(e);
        }
      }
    }
    if (failure != null) {
      throw failure;
    }
    return deleted;
  }

  private void endForAll(UUID userId, String sessionId) {
    sessionEnd.strict(
        new SessionEnd(userId.toString(), sessionId, SessionEndReason.ALL_DEVICES_REVOKED));
    sessions.delete(userId.toString(), sessionId);
  }
}
