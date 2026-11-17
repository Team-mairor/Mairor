package com.mairor.backend.common.security;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.event.EventListener;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.events.SessionExpiredEvent;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/** Runs the session end hooks when Redis expires a session. */
@Component
@ConditionalOnProperty(
    prefix = "spring.session.data.redis",
    name = "repository-type",
    havingValue = "indexed")
public class RedisSessionExpirationListener {

  private final SessionEndNotifier sessionEnd;

  public RedisSessionExpirationListener(SessionEndNotifier sessionEnd) {
    this.sessionEnd = sessionEnd;
  }

  @EventListener
  public void onSessionExpired(SessionExpiredEvent event) {
    String userId = principalName(event);
    if (!StringUtils.hasText(userId)) {
      return;
    }
    sessionEnd.bestEffort(
        new SessionEnd(userId, event.getSessionId(), SessionEndReason.IDLE_EXPIRED));
  }

  private static String principalName(SessionExpiredEvent event) {
    Object indexedName =
        event.getSession().getAttribute(FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME);
    if (indexedName instanceof String name && StringUtils.hasText(name)) {
      return name;
    }
    Object contextValue =
        event
            .getSession()
            .getAttribute(HttpSessionSecurityContextRepository.SPRING_SECURITY_CONTEXT_KEY);
    if (contextValue instanceof SecurityContext context) {
      Authentication authentication = context.getAuthentication();
      return authentication == null ? null : authentication.getName();
    }
    return null;
  }
}
