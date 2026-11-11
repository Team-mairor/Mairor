package com.mairor.backend.photos.service;

import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

/** 태그에 사진/회원 식별자나 저장소 키를 넣지 않는다. 대기 건수는 슬롯별 값이다. */
@Component
public class PhotoCleanupMetrics {
  private final MeterRegistry registry;
  private final AtomicLong overdue = new AtomicLong();

  public PhotoCleanupMetrics(MeterRegistry registry) {
    this.registry = registry;
    registry.gauge("mairor.photos.cleanup.overdue", overdue);
  }

  public void failed() {
    registry.counter("mairor.photos.cleanup.failures").increment();
  }

  public void overdue(long count) {
    overdue.set(count);
  }
}
