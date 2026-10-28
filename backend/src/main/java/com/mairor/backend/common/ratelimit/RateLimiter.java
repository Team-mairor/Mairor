package com.mairor.backend.common.ratelimit;

import java.time.Instant;

/**
 * 요청 제한. 같은 키(예: 클라이언트 IP)가 정해진 시간 안에 허용 횟수를 넘기면 막는다. 한도와 시간 창은 용도마다 구현체를 따로 만들어 정하고, {@link
 * #tryAcquire}는 키 단위로 원자적이어야 한다. 현재 시각은 호출자가 넘긴다.
 */
public interface RateLimiter {

  /** 한 번의 시도를 기록하고 허용 여부를 돌려준다. 막힌 시도는 횟수에 더해지지 않는다. */
  Decision tryAcquire(String key, Instant now);

  /**
   * 판정 결과.
   *
   * @param allowed 요청을 처리해도 되는지
   * @param retryAfterSeconds 막혔을 때 다시 시도할 수 있기까지 남은 초(1 이상). 허용이면 0
   */
  record Decision(boolean allowed, long retryAfterSeconds) {

    public static Decision permit() {
      return new Decision(true, 0);
    }

    public static Decision limited(long retryAfterSeconds) {
      return new Decision(false, retryAfterSeconds);
    }
  }
}
