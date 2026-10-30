package com.mairor.backend.testsupport;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;

/**
 * 테스트에서 시각을 옮길 수 있는 {@link Clock}. 필터와 서비스가 주입받는 시계만 움직인다. Spring Session 이 내부에서 쓰는 접근·만료 시각은 이 시계와
 * 무관하므로, 서버 유휴 만료는 {@code spring_session} 컬럼을 직접 조작해서 검증한다.
 */
public class MutableClock extends Clock {

  private volatile Instant instant;

  public MutableClock(Instant start) {
    this.instant = start;
  }

  public void set(Instant instant) {
    this.instant = instant;
  }

  public void advance(Duration duration) {
    this.instant = instant.plus(duration);
  }

  @Override
  public ZoneId getZone() {
    return ZoneOffset.UTC;
  }

  @Override
  public Clock withZone(ZoneId zone) {
    return this;
  }

  @Override
  public Instant instant() {
    return instant;
  }
}
