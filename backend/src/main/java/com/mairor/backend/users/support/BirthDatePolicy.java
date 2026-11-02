package com.mairor.backend.users.support;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import java.time.Clock;
import java.time.LocalDate;
import java.time.Period;
import java.time.ZoneId;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * 가입 생년월일 규칙. 자체 가입과 Google 가입이 같이 쓴다. 입력했을 때만 확인하고, 어기면 400 {@code VALIDATION_FAILED}({@code
 * details[].field = birthDate}).
 */
@Component
public class BirthDatePolicy {

  /** 만 14세 기준과 "오늘"은 한국 날짜로 센다. */
  private static final ZoneId SERVICE_ZONE = ZoneId.of("Asia/Seoul");

  private static final LocalDate EARLIEST_BIRTH_DATE = LocalDate.of(1900, 1, 1);
  private static final int MIN_AGE = 14;

  private final Clock clock;

  public BirthDatePolicy(Clock clock) {
    this.clock = clock;
  }

  /** 오늘보다 과거, 1900-01-01 이후, 만 14세 이상. {@code null} 이면 확인하지 않는다. */
  public void validate(LocalDate birthDate) {
    if (birthDate == null) {
      return;
    }
    LocalDate today = LocalDate.now(clock.withZone(SERVICE_ZONE));
    if (!birthDate.isBefore(today)) {
      throw birthDateInvalid("과거 날짜여야 합니다.");
    }
    if (birthDate.isBefore(EARLIEST_BIRTH_DATE)) {
      throw birthDateInvalid("1900-01-01 이후여야 합니다.");
    }
    if (Period.between(birthDate, today).getYears() < MIN_AGE) {
      throw birthDateInvalid("만 14세 이상만 가입할 수 있습니다.");
    }
  }

  private static BusinessException birthDateInvalid(String reason) {
    return new BusinessException(
        HttpStatus.BAD_REQUEST,
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError("birthDate", reason)),
        null);
  }
}
