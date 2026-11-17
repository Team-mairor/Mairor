package com.mairor.backend.common.security;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

/**
 * 세션 처리 장애 지표. 반복되는 장애를 알아채려는 용도라서 값은 건수뿐이고, 이메일·세션 ID·사용자 ID 는 라벨에 넣지 않는다(라벨은 아래의 고정된 몇 가지 값만 쓴다).
 *
 * <ul>
 *   <li>{@code mairor.session.failures{cause}}: 필터 단계에서 세션을 읽거나 저장·삭제하다 실패한 횟수. {@code cause} 는
 *       {@code store_unavailable}(DB 장애), {@code corrupted_session}(손상된 세션), {@code unexpected}.
 *       조회·저장·삭제 중 어느 쪽이었는지는 예외만으로는 알 수 없어서 나누지 않는다. 로그의 스택으로 확인한다.
 *   <li>{@code mairor.session.cookie_refresh.failures}: 세션 쿠키 갱신 실패 횟수. 갱신이 실패해도 업무 응답은 그대로 나가므로,
 *       반복되는지는 이 지표로 본다.
 *   <li>{@code mairor.session.end_hook.failures{reason}}: 세션 종료 훅({@link SessionEndHook})이 실패한 횟수.
 *       {@code reason} 은 {@link SessionEndReason} 의 소문자 이름이다. 어느 훅이 실패했는지는 로그로 본다.
 * </ul>
 */
@Component
public class SessionMetrics {

  static final String FAILURES = "mairor.session.failures";
  static final String COOKIE_REFRESH_FAILURES = "mairor.session.cookie_refresh.failures";
  static final String END_HOOK_FAILURES = "mairor.session.end_hook.failures";

  private final MeterRegistry registry;

  public SessionMetrics(MeterRegistry registry) {
    this.registry = registry;
  }

  void failure(SessionStoreFailureFilter.Cause cause) {
    registry
        .counter(FAILURES, "cause", cause.name().toLowerCase(java.util.Locale.ROOT))
        .increment();
  }

  void cookieRefreshFailure() {
    registry.counter(COOKIE_REFRESH_FAILURES).increment();
  }

  void endHookFailure(SessionEndReason reason) {
    registry
        .counter(END_HOOK_FAILURES, "reason", reason.name().toLowerCase(java.util.Locale.ROOT))
        .increment();
  }
}
