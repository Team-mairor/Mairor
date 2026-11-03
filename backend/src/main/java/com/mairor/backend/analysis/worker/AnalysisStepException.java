package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import java.util.Objects;

/** 단계 처리기가 원인을 분류한 실패. 실행기가 이 코드로 작업을 FAILED 로 끝낸다. 분류하지 못한 예외는 {@code INTERNAL_ERROR}가 된다. */
public class AnalysisStepException extends RuntimeException {

  private final AnalysisFailureCode code;

  public AnalysisStepException(AnalysisFailureCode code, String message, Throwable cause) {
    super(message, cause);
    this.code = Objects.requireNonNull(code, "code");
  }

  public AnalysisStepException(AnalysisFailureCode code, String message) {
    this(code, message, null);
  }

  public AnalysisFailureCode code() {
    return code;
  }
}
