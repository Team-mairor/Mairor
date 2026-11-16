package com.mairor.backend.analysis.service;

import java.util.function.Supplier;
import org.springframework.dao.DataIntegrityViolationException;

/** 등록 트랜잭션이 동시 요청으로 충돌하면 새 트랜잭션에서 한 번 재시도한다. */
final class AnalysisRegistrationRetry {

  private AnalysisRegistrationRetry() {}

  static <T> T onceAfterConflict(Supplier<T> registration, Runnable onConflict) {
    try {
      return registration.get();
    } catch (DataIntegrityViolationException conflict) {
      onConflict.run();
      return registration.get();
    }
  }
}
