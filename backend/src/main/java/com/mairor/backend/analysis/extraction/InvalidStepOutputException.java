package com.mairor.backend.analysis.extraction;

/** 단계 추출 답의 모양 자체가 틀렸다(JSON 아님, {@code steps} 없음). 단계 하나가 틀린 것은 버리고 넘어간다. */
public class InvalidStepOutputException extends RuntimeException {

  public InvalidStepOutputException(String message, Throwable cause) {
    super(message, cause);
  }
}
