package com.mairor.backend.users.service;

import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import com.mairor.backend.common.security.SessionEndNotifier;
import com.mairor.backend.common.security.SessionEndReason;
import com.mairor.backend.common.security.SessionLifetimePolicy;
import com.mairor.backend.users.dto.response.SessionItemResponse;
import com.mairor.backend.users.support.UserSessionAttributes;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

/**
 * 로그인 기기 관리: 내 기기 목록, 기기 하나 로그아웃, 전체 로그아웃.
 *
 * <p>세션은 {@link FindByIndexNameSessionRepository} 로만 다룬다(저장소 테이블에 직접 SQL 을 쓰지 않는다). Spring Session
 * 이 {@code PRINCIPAL_NAME} 을 userId 로 색인하므로 회원의 세션을 찾을 수 있다. 다른 회원의 세션은 조회 결과에 들어오지 않으므로, 기기 하나를 지울
 * 때도 <b>이 회원의 목록 안에서 {@code sessionRef} 가 일치하는 것만</b> 지운다. URL 의 값으로 세션 ID 를 직접 지우지 않는다.
 *
 * <p>보장 범위: 호출 시점에 조회된 세션을 지운다. 지우는 도중에 막 시작된 로그인이 나중에 발급한 세션이나 이미 인증을 통과해 실행 중인 요청은 막지 못한다.
 */
@Service
public class UserSessionService {

  private final FindByIndexNameSessionRepository<? extends Session> sessions;
  private final SessionLifetimePolicy policy;
  private final SessionEndNotifier sessionEnd;
  private final Clock clock;

  public UserSessionService(
      FindByIndexNameSessionRepository<? extends Session> sessions,
      SessionLifetimePolicy policy,
      SessionEndNotifier sessionEnd,
      Clock clock) {
    this.sessions = sessions;
    this.policy = policy;
    this.sessionEnd = sessionEnd;
    this.clock = clock;
  }

  /** 아직 유효한 내 기기 목록. 마지막 요청이 가장 최근인 기기가 앞에 온다. */
  public List<SessionItemResponse> list(UUID userId, String currentSessionId) {
    return activeSessions(userId).stream()
        .sorted(
            Comparator.comparing((ActiveSession s) -> s.session().getLastAccessedTime()).reversed())
        .map(
            s ->
                new SessionItemResponse(
                    s.ref().toString(),
                    deviceOf(s.session()),
                    s.loggedInAt(),
                    s.session().getLastAccessedTime(),
                    s.session().getId().equals(currentSessionId)))
        .toList();
  }

  /**
   * 현재 기기를 로그아웃하기 직전의 정리. 세션을 끝내는 쪽({@code CurrentSessionEnder})을 부르기 <b>전에</b> 호출한다. 종료 훅이 실패하면
   * 예외를 던지고, 그러면 호출한 쪽이 세션을 끝내지 않으므로 회원은 세션이 남은 채 같은 요청을 다시 보낼 수 있다.
   */
  public void beforeLogout(UUID userId, String currentSessionId) {
    sessionEnd.strict(new SessionEnd(userId.toString(), currentSessionId, SessionEndReason.LOGOUT));
  }

  /**
   * 내 기기 하나를 로그아웃시킨다. 세션을 지우기 <b>전에</b> 종료 훅을 호출하고, 훅이 실패하면 세션을 지우지 않고 예외를 던진다.
   *
   * @param currentSessionId 요청을 보낸 세션의 ID. 지정한 기기가 이 세션이면 로그아웃과 같으므로 종료 이유가 {@code LOGOUT} 이다. 없으면
   *     {@code null}
   * @return 지운 세션의 ID. 이 회원에게 그 {@code sessionRef} 의 유효한 기기가 없으면(없는 값·이미 끝남·다른 회원의 값) 빈 값
   */
  public Optional<String> revoke(UUID userId, UUID sessionRef, String currentSessionId) {
    return activeSessions(userId).stream()
        .filter(s -> s.ref().equals(sessionRef))
        .findFirst()
        .map(
            s -> {
              String id = s.session().getId();
              SessionEndReason reason =
                  id.equals(currentSessionId)
                      ? SessionEndReason.LOGOUT
                      : SessionEndReason.DEVICE_REVOKED;
              sessionEnd.strict(new SessionEnd(userId.toString(), id, reason));
              sessions.deleteById(id);
              return id;
            });
  }

  /**
   * 내 모든 기기를 로그아웃시킨다. 유효하지 않거나 기기 정보가 없는 세션도 함께 지운다. 현재 세션({@code currentSessionId})은 다른 세션을 모두 지운
   * 뒤 마지막에 지운다. 요청이 들고 있는 현재 세션은 응답을 커밋할 때 되살아날 수 있으므로 호출자가 따로 끝내야 한다({@code CurrentSessionEnder}).
   *
   * <p>세션마다 지우기 <b>전에</b> 종료 훅({@link SessionEndHook})을 호출한다. 훅이 실패한 세션은 지우지 않는다.
   *
   * <p><b>원자적이지 않다.</b> 세션은 하나씩 지우고, Spring Session JDBC 는 삭제마다 별도 트랜잭션을 쓰므로 {@code @Transactional}
   * 로 묶어도 되돌려지지 않는다. 도중에 정리하지 못한 세션(훅 또는 삭제 실패)이 있으면 나머지는 끝까지 시도하고, 현재 세션은 지우지 않은 채 첫 번째 실패를
   * 던진다(나머지 실패는 suppressed 로 붙는다). 현재 기기가 살아 있으므로 같은 요청을 다시 보내 마무리할 수 있다. 이미 끝난 세션은 다시 조회되지 않아 훅이
   * 다시 호출되지 않는다.
   *
   * @param currentSessionId 요청을 보낸 세션의 ID. 없거나 이 회원의 세션이 아니면 {@code null} 로 두거나 무시된다
   * @return 지운 세션 수
   */
  public int revokeAll(UUID userId, String currentSessionId) {
    List<String> others = new ArrayList<>();
    boolean hasCurrent = false;
    for (String id : sessions.findByPrincipalName(userId.toString()).keySet()) {
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

  private void endForAll(UUID userId, String sessionId) {
    sessionEnd.strict(
        new SessionEnd(userId.toString(), sessionId, SessionEndReason.ALL_DEVICES_REVOKED));
    sessions.deleteById(sessionId);
  }

  private record ActiveSession(Session session, UUID ref, Instant loggedInAt) {}

  /** 만료되지 않았고 기기 식별자·로그인 시각이 있는 세션. 절대 만료가 지난 세션은 아직 정리되지 않았어도 제외한다. */
  private List<ActiveSession> activeSessions(UUID userId) {
    Instant now = clock.instant();
    List<ActiveSession> active = new ArrayList<>();
    for (Session session : sessions.findByPrincipalName(userId.toString()).values()) {
      if (session.isExpired()) {
        continue;
      }
      Object ref = session.getAttribute(UserSessionAttributes.SESSION_REF);
      Object authenticatedAt = session.getAttribute(SessionAttributes.AUTHENTICATED_AT);
      if (!(ref instanceof UUID sessionRef) || !(authenticatedAt instanceof Instant loggedInAt)) {
        continue;
      }
      if (policy.isAbsolutelyExpired(loggedInAt, now)) {
        continue;
      }
      active.add(new ActiveSession(session, sessionRef, loggedInAt));
    }
    return active;
  }

  private static String deviceOf(Session session) {
    Object device = session.getAttribute(UserSessionAttributes.DEVICE);
    return device instanceof String text ? text : "알 수 없는 기기";
  }
}
