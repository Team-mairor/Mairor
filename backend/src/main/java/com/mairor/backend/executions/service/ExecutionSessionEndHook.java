package com.mairor.backend.executions.service;

import com.mairor.backend.common.security.SessionEnd;
import com.mairor.backend.common.security.SessionEndHook;
import java.util.UUID;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/** 세션이 종료되기 전에 해당 세션의 미완료 GUIDE 실행과 임시 사진을 정리한다. */
@Component
@Order(200)
public class ExecutionSessionEndHook implements SessionEndHook {
  private final ExecutionLifecycleService lifecycle;

  public ExecutionSessionEndHook(ExecutionLifecycleService lifecycle) {
    this.lifecycle = lifecycle;
  }

  @Override
  public void beforeSessionEnds(SessionEnd end) {
    UUID userId;
    try {
      userId = UUID.fromString(end.userId());
    } catch (IllegalArgumentException ignored) {
      return;
    }
    lifecycle.abandonSession(userId, end.sessionId());
  }
}
