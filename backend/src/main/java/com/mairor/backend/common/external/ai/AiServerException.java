package com.mairor.backend.common.external.ai;

/** AI 서버 호출 실패. {@code status}는 HTTP 상태이고 연결 실패면 null 이다. */
public class AiServerException extends RuntimeException {

  private final Integer status;

  public AiServerException(String message, Integer status, Throwable cause) {
    super(message, cause);
    this.status = status;
  }

  public Integer status() {
    return status;
  }
}
