package com.mairor.backend.common.error;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * 모든 오류 응답의 본문. 노션 API 명세 공통 규약과 AI 서버의 {@code ErrorResponse}와 같은 모양이다.
 *
 * <pre>
 * {"code": "VALIDATION_FAILED", "message": "입력값이 올바르지 않습니다.", "details": [{"field": "size", "reason": "..."}]}
 * </pre>
 *
 * {@code details}는 입력 필드 오류일 때만 들어가고, 없으면 생략된다.
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ErrorResponse(String code, String message, List<FieldError> details) {

  /** 입력 필드 하나의 오류. */
  public record FieldError(String field, String reason) {}

  public static ErrorResponse of(ErrorCode code) {
    return new ErrorResponse(code.name(), code.message(), null);
  }

  public static ErrorResponse of(ErrorCode code, List<FieldError> details) {
    return new ErrorResponse(code.name(), code.message(), emptyToNull(details));
  }

  public static ErrorResponse of(String code, String message, List<FieldError> details) {
    return new ErrorResponse(code, message, emptyToNull(details));
  }

  private static List<FieldError> emptyToNull(List<FieldError> details) {
    return details == null || details.isEmpty() ? null : List.copyOf(details);
  }
}
