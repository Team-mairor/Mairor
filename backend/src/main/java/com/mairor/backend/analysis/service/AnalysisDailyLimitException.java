package com.mairor.backend.analysis.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import org.springframework.http.HttpStatus;

/**
 * 회원별 일일 신규 분석 한도 초과(API-VIDEO-002 429 {@code ANALYSIS_DAILY_LIMIT_EXCEEDED}). {@code Retry-After}
 * 헤더(초)와 오류 본문 {@code resetAt}(다음 초기화 시각)을 함께 준다.
 */
public class AnalysisDailyLimitException extends BusinessException {

  public static final String CODE = "ANALYSIS_DAILY_LIMIT_EXCEEDED";

  private final Instant resetAt;

  AnalysisDailyLimitException(Instant resetAt, Instant now) {
    super(
        HttpStatus.TOO_MANY_REQUESTS,
        CODE,
        "오늘 새로 분석할 수 있는 횟수를 다 썼습니다. 가이드가 있는 영상은 바로 따라 할 수 있습니다.",
        null,
        retryAfterSeconds(resetAt, now));
    this.resetAt = Objects.requireNonNull(resetAt, "resetAt");
  }

  /** 초기화까지 남은 초, 올림. 최소 1. */
  static long retryAfterSeconds(Instant resetAt, Instant now) {
    Duration left = Duration.between(now, resetAt);
    long seconds = left.getSeconds() + (left.getNano() > 0 ? 1 : 0);
    return Math.max(1, seconds);
  }

  public Instant resetAt() {
    return resetAt;
  }

  @Override
  public ErrorResponse toResponse() {
    ErrorResponse base = super.toResponse();
    return new ErrorResponse(base.code(), base.message(), base.details(), resetAt);
  }
}
