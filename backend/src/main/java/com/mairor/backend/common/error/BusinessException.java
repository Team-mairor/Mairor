package com.mairor.backend.common.error;

import java.util.List;
import org.springframework.http.HttpStatus;

/**
 * 업무 규칙 위반을 나타내는 예외. {@link GlobalExceptionHandler}가 {@link ErrorResponse}로 바꾼다. AI 서버의 {@code
 * AppError(status, code, message)}와 같은 역할이다.
 *
 * <pre>
 * throw new BusinessException(ErrorCode.NOT_FOUND);                       // 공통 코드
 * throw new BusinessException(HttpStatus.CONFLICT, "ANALYSIS_IN_PROGRESS", "이미 분석 중인 영상입니다."); // 도메인 코드
 * throw BusinessException.tooManyRequests(30);                            // 429 + Retry-After: 30
 * </pre>
 */
public class BusinessException extends RuntimeException {

  private final HttpStatus status;
  private final String code;
  private final transient List<ErrorResponse.FieldError> details;
  private final Long retryAfterSeconds;

  public BusinessException(ErrorCode code) {
    this(code.status(), code.name(), code.message(), null, null);
  }

  public BusinessException(ErrorCode code, String message) {
    this(code.status(), code.name(), message, null, null);
  }

  public BusinessException(HttpStatus status, String code, String message) {
    this(status, code, message, null, null);
  }

  public BusinessException(
      HttpStatus status,
      String code,
      String message,
      List<ErrorResponse.FieldError> details,
      Long retryAfterSeconds) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details == null ? List.of() : List.copyOf(details);
    this.retryAfterSeconds = retryAfterSeconds;
  }

  /** 429 응답. {@code Retry-After} 헤더에 초 단위 값을 싣는다. */
  public static BusinessException tooManyRequests(long retryAfterSeconds) {
    ErrorCode code = ErrorCode.TOO_MANY_REQUESTS;
    return new BusinessException(
        code.status(), code.name(), code.message(), null, retryAfterSeconds);
  }

  public HttpStatus status() {
    return status;
  }

  public String code() {
    return code;
  }

  public List<ErrorResponse.FieldError> details() {
    return details;
  }

  public Long retryAfterSeconds() {
    return retryAfterSeconds;
  }

  public ErrorResponse toResponse() {
    return ErrorResponse.of(code, getMessage(), details);
  }
}
