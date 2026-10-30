package com.mairor.backend.users.support;

import io.micrometer.core.instrument.MeterRegistry;
import java.util.Locale;
import org.springframework.stereotype.Component;

/**
 * 로그인 결과 지표 {@code mairor.login.attempts{result}}. 결과별 건수만 센다. 이메일·사용자 ID·IP 는 라벨에 넣지 않는다(라벨 값은
 * {@link Result} 의 고정된 몇 가지뿐이다).
 */
@Component
public class LoginMetrics {

  static final String ATTEMPTS = "mairor.login.attempts";

  /** 로그인 한 번의 결과. 지표 라벨 값은 이름의 소문자다. */
  public enum Result {
    /** 로그인에 성공해 세션을 만들었다. */
    SUCCESS,
    /** 이메일 또는 비밀번호가 맞지 않았다. */
    INVALID_CREDENTIALS,
    /** 반복 실패로 잠긴 이메일의 시도. */
    LOCKED,
    /** 같은 이메일의 시도가 한도까지 진행 중이라 새 시도를 받지 않았다. */
    PENDING,
    /** 시도 제한 저장소가 가득 차서 새 이메일을 받지 않았다. */
    SATURATED,
    /** 서버 전체 동시 처리 상한(해시 게이트)에 걸려 거절했다. */
    GATE_REJECTED,
    /** 자격 증명과 무관한 내부 오류. */
    ERROR
  }

  private final MeterRegistry registry;

  public LoginMetrics(MeterRegistry registry) {
    this.registry = registry;
  }

  public void record(Result result) {
    registry.counter(ATTEMPTS, "result", result.name().toLowerCase(Locale.ROOT)).increment();
  }
}
