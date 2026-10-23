package com.mairor.backend.common.error;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.MessageSourceResolvable;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.validation.FieldError;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 컨트롤러 단계에서 나는 모든 예외를 {@link ErrorResponse} 형식으로 바꾼다.
 *
 * <p>시큐리티 필터 단계(미인증 401, CSRF·권한 403)는 컨트롤러 밖이라 여기 오지 않는다. 그 경우는 {@link
 * com.mairor.backend.common.security.SecurityConfig}가 {@link ErrorResponseWriter}로 같은 형식을 쓴다.
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

  private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

  /** 업무 예외: 예외가 가진 상태·코드·메시지를 그대로 쓴다. 429면 Retry-After 헤더를 붙인다. */
  @ExceptionHandler(BusinessException.class)
  public ResponseEntity<ErrorResponse> handleBusiness(BusinessException e) {
    HttpHeaders headers = new HttpHeaders();
    if (e.retryAfterSeconds() != null) {
      headers.add(HttpHeaders.RETRY_AFTER, String.valueOf(e.retryAfterSeconds()));
    }
    return ResponseEntity.status(e.status()).headers(headers).body(e.toResponse());
  }

  /** {@code @Valid} 요청 본문·{@code @ModelAttribute} 파라미터 검증 실패. */
  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<ErrorResponse> handleMethodArgumentNotValid(
      MethodArgumentNotValidException e) {
    List<ErrorResponse.FieldError> details = new ArrayList<>();
    for (FieldError fe : e.getBindingResult().getFieldErrors()) {
      details.add(new ErrorResponse.FieldError(fe.getField(), fe.getDefaultMessage()));
    }
    return validationFailed(details);
  }

  /** {@code @RequestParam}·{@code @PathVariable} 등 메서드 파라미터 제약 위반. */
  @ExceptionHandler(HandlerMethodValidationException.class)
  public ResponseEntity<ErrorResponse> handleHandlerMethodValidation(
      HandlerMethodValidationException e) {
    List<ErrorResponse.FieldError> details = new ArrayList<>();
    e.getParameterValidationResults()
        .forEach(
            result -> {
              String name = result.getMethodParameter().getParameterName();
              for (MessageSourceResolvable error : result.getResolvableErrors()) {
                String field = error instanceof FieldError fe ? fe.getField() : name;
                details.add(new ErrorResponse.FieldError(field, error.getDefaultMessage()));
              }
            });
    return validationFailed(details);
  }

  /** 서비스 계층 등에서 난 Bean Validation 위반. */
  @ExceptionHandler(ConstraintViolationException.class)
  public ResponseEntity<ErrorResponse> handleConstraintViolation(ConstraintViolationException e) {
    List<ErrorResponse.FieldError> details = new ArrayList<>();
    for (ConstraintViolation<?> v : e.getConstraintViolations()) {
      details.add(
          new ErrorResponse.FieldError(lastNode(v.getPropertyPath().toString()), v.getMessage()));
    }
    return validationFailed(details);
  }

  /** 파라미터 타입 불일치 (예: page=abc). */
  @ExceptionHandler(MethodArgumentTypeMismatchException.class)
  public ResponseEntity<ErrorResponse> handleTypeMismatch(MethodArgumentTypeMismatchException e) {
    return validationFailed(
        List.of(new ErrorResponse.FieldError(e.getName(), "값의 형식이 올바르지 않습니다.")));
  }

  /** 필수 파라미터 누락. */
  @ExceptionHandler(MissingServletRequestParameterException.class)
  public ResponseEntity<ErrorResponse> handleMissingParameter(
      MissingServletRequestParameterException e) {
    return validationFailed(
        List.of(new ErrorResponse.FieldError(e.getParameterName(), "필수 값입니다.")));
  }

  /** 요청 본문을 읽을 수 없음 (JSON 문법 오류, 빈 본문 등). */
  @ExceptionHandler(HttpMessageNotReadableException.class)
  public ResponseEntity<ErrorResponse> handleNotReadable(HttpMessageNotReadableException e) {
    return validationFailed(List.of(new ErrorResponse.FieldError("body", "요청 본문을 읽을 수 없습니다.")));
  }

  /** 없는 경로. */
  @ExceptionHandler(NoResourceFoundException.class)
  public ResponseEntity<ErrorResponse> handleNoResource(NoResourceFoundException e) {
    return of(ErrorCode.NOT_FOUND);
  }

  /** 허용되지 않는 메서드. */
  @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
  public ResponseEntity<ErrorResponse> handleMethodNotSupported(
      HttpRequestMethodNotSupportedException e) {
    return of(ErrorCode.METHOD_NOT_ALLOWED);
  }

  /** 컨트롤러 안에서 난 인증 예외 (필터 밖). */
  @ExceptionHandler(AuthenticationException.class)
  public ResponseEntity<ErrorResponse> handleAuthentication(AuthenticationException e) {
    return of(ErrorCode.UNAUTHORIZED);
  }

  /** 컨트롤러 안에서 난 권한 예외 (예: {@code @PreAuthorize}). */
  @ExceptionHandler(AccessDeniedException.class)
  public ResponseEntity<ErrorResponse> handleAccessDenied(AccessDeniedException e) {
    return of(ErrorCode.FORBIDDEN);
  }

  /** 그 밖의 스프링 표준 HTTP 오류 (415 등): 상태 코드 이름을 코드로 쓴다. AI 서버와 같은 규칙. */
  @ExceptionHandler(ErrorResponseException.class)
  public ResponseEntity<ErrorResponse> handleErrorResponse(ErrorResponseException e) {
    HttpStatus status = HttpStatus.resolve(e.getStatusCode().value());
    String code = status != null ? status.name() : "HTTP_" + e.getStatusCode().value();
    String message = status != null ? status.getReasonPhrase() : "요청을 처리할 수 없습니다.";
    return ResponseEntity.status(e.getStatusCode()).body(ErrorResponse.of(code, message, null));
  }

  /** 처리하지 못한 예외: 내부 정보는 응답에 넣지 않고 로그에만 남긴다. */
  @ExceptionHandler(Exception.class)
  public ResponseEntity<ErrorResponse> handleUnexpected(Exception e) {
    log.error("처리하지 못한 예외", e);
    return of(ErrorCode.INTERNAL_ERROR);
  }

  private static ResponseEntity<ErrorResponse> validationFailed(
      List<ErrorResponse.FieldError> details) {
    return ResponseEntity.status(ErrorCode.VALIDATION_FAILED.status())
        .body(ErrorResponse.of(ErrorCode.VALIDATION_FAILED, details));
  }

  private static ResponseEntity<ErrorResponse> of(ErrorCode code) {
    return ResponseEntity.status(code.status()).body(ErrorResponse.of(code));
  }

  private static String lastNode(String propertyPath) {
    int dot = propertyPath.lastIndexOf('.');
    return dot < 0 ? propertyPath : propertyPath.substring(dot + 1);
  }
}
