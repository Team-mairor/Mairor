package com.mairor.backend.common.error;

import org.springframework.http.HttpStatus;

/**
 * 공통 오류 코드. 노션 API 명세 "공통 오류 코드" 표의 code·기본 message와 같다. AI 서버({@code ai/app/core/errors.py})와도 같은
 * 값을 쓰고, 브라우저 세션 전용인 {@link #CSRF_INVALID}만 백엔드에만 있다.
 *
 * <p>도메인 고유 코드(예: {@code ANALYSIS_IN_PROGRESS})는 여기 넣지 않고 {@link BusinessException}에 상태·코드·메시지를 직접
 * 넘긴다.
 */
public enum ErrorCode {
  VALIDATION_FAILED(HttpStatus.BAD_REQUEST, "입력값이 올바르지 않습니다."),
  UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "로그인이 필요합니다."),
  /** 변경 요청(POST·PUT·PATCH·DELETE)의 CSRF 토큰 없음·불일치. FE는 내 계정 조회로 토큰을 다시 받는다. */
  CSRF_INVALID(HttpStatus.FORBIDDEN, "요청 보안 토큰이 유효하지 않습니다."),
  FORBIDDEN(HttpStatus.FORBIDDEN, "요청 권한이 없습니다."),
  NOT_FOUND(HttpStatus.NOT_FOUND, "요청한 리소스를 찾을 수 없습니다."),
  METHOD_NOT_ALLOWED(HttpStatus.METHOD_NOT_ALLOWED, "허용되지 않는 요청 방식입니다."),
  CONFLICT(HttpStatus.CONFLICT, "요청이 현재 상태와 충돌합니다."),
  TOO_MANY_REQUESTS(HttpStatus.TOO_MANY_REQUESTS, "요청 한도를 초과했습니다."),
  INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "서버에서 예기치 않은 오류가 발생했습니다.");

  private final HttpStatus status;
  private final String message;

  ErrorCode(HttpStatus status, String message) {
    this.status = status;
    this.message = message;
  }

  public HttpStatus status() {
    return status;
  }

  public String message() {
    return message;
  }
}
