package com.mairor.backend.common.external.youtube;

/** YouTube Data API 호출 실패. 어느 오류 응답으로 바꿀지는 부르는 쪽이 {@link Kind}로 정한다. */
public class YouTubeException extends RuntimeException {

  /** 실패 종류. */
  public enum Kind {
    /** 키가 없다(설정 누락). */
    NOT_CONFIGURED,
    /** 하루 할당량을 다 썼다(403 quotaExceeded · dailyLimitExceeded). */
    QUOTA_EXCEEDED,
    /** 제한 시간 안에 답이 없었다. */
    TIMEOUT,
    /** 연결 실패, 5xx, 그 밖에 쓸 수 없는 답. */
    UNAVAILABLE
  }

  private final Kind kind;

  public YouTubeException(Kind kind, String message, Throwable cause) {
    super(message, cause);
    this.kind = kind;
  }

  public Kind kind() {
    return kind;
  }
}
