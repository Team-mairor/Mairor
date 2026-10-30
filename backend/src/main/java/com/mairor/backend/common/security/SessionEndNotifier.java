package com.mairor.backend.common.security;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

/**
 * 등록된 {@link SessionEndHook} 을 {@code @Order} 순으로 호출한다. 호출하는 쪽이 실패를 어떻게 다룰지에 따라 두 가지로 부른다.
 *
 * <ul>
 *   <li>{@link #strict}: 훅이 실패하면 그 예외를 그대로 던진다. 뒤 훅은 호출하지 않는다. 호출하는 쪽이 세션을 남기고 오류로 응답하거나 재시도를 맡긴다.
 *   <li>{@link #bestEffort}: 훅이 실패해도 삼키고 나머지 훅을 계속 호출한다. 호출하는 쪽의 흐름(로그인 등)을 막으면 안 될 때 쓴다.
 * </ul>
 *
 * 어느 쪽이든 실패하면 지표({@code mairor.session.end_hook.failures{reason}})와 로그를 남긴다. 로그에는 훅 클래스 이름과 종료 이유를
 * 쓰고 세션 ID 는 쓰지 않는다. 훅이 하나도 없으면 아무 일도 하지 않는다.
 */
@Component
public class SessionEndNotifier {

  private static final Logger log = LoggerFactory.getLogger(SessionEndNotifier.class);

  private final ObjectProvider<SessionEndHook> hooks;
  private final SessionMetrics metrics;

  public SessionEndNotifier(ObjectProvider<SessionEndHook> hooks, SessionMetrics metrics) {
    this.hooks = hooks;
    this.metrics = metrics;
  }

  /** 훅이 실패하면 그 예외를 던진다. 뒤 훅은 호출하지 않는다. */
  public void strict(SessionEnd end) {
    for (SessionEndHook hook : (Iterable<SessionEndHook>) hooks.orderedStream()::iterator) {
      try {
        hook.beforeSessionEnds(end);
      } catch (RuntimeException e) {
        recordFailure(hook, end, e);
        throw e;
      }
    }
  }

  /** 훅이 실패해도 삼키고 나머지 훅을 계속 호출한다. */
  public void bestEffort(SessionEnd end) {
    for (SessionEndHook hook : (Iterable<SessionEndHook>) hooks.orderedStream()::iterator) {
      try {
        hook.beforeSessionEnds(end);
      } catch (RuntimeException e) {
        recordFailure(hook, end, e);
      }
    }
  }

  private void recordFailure(SessionEndHook hook, SessionEnd end, RuntimeException e) {
    metrics.endHookFailure(end.reason());
    // 세션 ID 는 SessionEnd#toString 이 가리지만, 로그에는 이유와 훅 이름만 쓴다
    log.error("세션 종료 훅이 실패했습니다. 훅: {}, 이유: {}", hook.getClass().getName(), end.reason(), e);
  }
}
