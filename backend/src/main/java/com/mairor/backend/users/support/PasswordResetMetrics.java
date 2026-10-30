package com.mairor.backend.users.support;

import io.micrometer.core.instrument.MeterRegistry;
import java.util.Locale;
import org.springframework.stereotype.Component;

/**
 * 비밀번호 재설정 지표 {@code mairor.password_reset{result}}. 결과별 건수만 센다. 이메일·사용자 ID·IP 는 라벨에 넣지 않는다.
 *
 * <p>운영에서 특히 볼 것은 {@link Result#SESSION_REVOKE_FAILED}다. 비밀번호는 바뀌었는데 기존 세션을 다 끊지 못한 경우라, 사용자가 다시
 * 요청하지 않으면 옛 세션이 남는다.
 */
@Component
public class PasswordResetMetrics {

  static final String NAME = "mairor.password_reset";

  /** 비밀번호 재설정 요청 하나의 결과. 지표 라벨 값은 이름의 소문자다. */
  public enum Result {
    /** 새 비밀번호를 저장하고 기존 세션을 모두 끝냈다. */
    SUCCESS,
    /** 새 비밀번호는 저장했지만 기존 세션을 모두 끝내지 못했다. 같은 토큰으로 다시 요청해야 마무리된다. */
    SESSION_REVOKE_FAILED,
    /** 같은 이메일의 다른 재설정 요청이 처리 중이라 거절했다. */
    BUSY
  }

  private final MeterRegistry registry;

  public PasswordResetMetrics(MeterRegistry registry) {
    this.registry = registry;
  }

  public void record(Result result) {
    registry.counter(NAME, "result", result.name().toLowerCase(Locale.ROOT)).increment();
  }
}
