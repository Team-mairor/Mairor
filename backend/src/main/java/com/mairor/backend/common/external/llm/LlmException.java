package com.mairor.backend.common.external.llm;

import java.util.Objects;

/** LLM 호출 실패. 재시도할 만한지는 {@link Kind}로 나눈다. */
public class LlmException extends RuntimeException {

  public enum Kind {
    /** 키가 없다. 설정을 고치기 전에는 계속 실패한다. */
    NOT_CONFIGURED,
    /** 연결 실패·시간 초과·429·5xx. 재시도를 다 썼다. */
    UNAVAILABLE,
    /** 4xx(429 제외). 요청이나 키가 잘못됐다. */
    REJECTED,
    /** 200 이지만 답을 쓸 수 없다(후보 없음·차단·잘림). */
    INVALID_RESPONSE
  }

  private final Kind kind;
  private final Integer status;
  private final String provider;
  private final String model;

  public LlmException(
      Kind kind, String message, Integer status, String provider, String model, Throwable cause) {
    super(message, cause);
    this.kind = Objects.requireNonNull(kind, "kind");
    this.status = status;
    this.provider = provider;
    this.model = model;
  }

  public Kind kind() {
    return kind;
  }

  /** HTTP 상태. 연결 실패처럼 응답이 없으면 null. */
  public Integer status() {
    return status;
  }

  public String provider() {
    return provider;
  }

  public String model() {
    return model;
  }
}
