package com.mairor.backend.users.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.dto.request.SignUpRequest;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.transaction.annotation.Transactional;

/** 생년월일 범위(과거·1900년 이후·만 14세)를 시각을 고정해 확인한다. 고정한 "지금"은 한국 시간 2026-10-27 09:00 이다. */
@Import({TestcontainersConfiguration.class, UserSignUpBirthDateTest.FixedClockConfig.class})
@SpringBootTest
@Transactional
class UserSignUpBirthDateTest {

  @TestConfiguration
  static class FixedClockConfig {
    @Bean
    @Primary
    Clock fixedClock() {
      return Clock.fixed(Instant.parse("2026-10-27T00:00:00Z"), ZoneOffset.UTC);
    }
  }

  @Autowired private UserSignUpService service;

  private static SignUpRequest requestWithBirthDate(String birthDate) {
    return new SignUpRequest(
        "a@example.com",
        "ExampleOnly!2026",
        "ExampleOnly!2026",
        null,
        null,
        null,
        LocalDate.parse(birthDate),
        null,
        SignUpRequests.requiredAgreements(),
        null);
  }

  private void assertRejected(String birthDate, String reason) {
    assertThatThrownBy(() -> service.signUp(requestWithBirthDate(birthDate)))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> {
              assertThat(e.status().value()).isEqualTo(400);
              assertThat(e.toResponse().code()).isEqualTo("VALIDATION_FAILED");
              assertThat(e.toResponse().details())
                  .singleElement()
                  .satisfies(
                      d -> {
                        assertThat(d.field()).isEqualTo("birthDate");
                        assertThat(d.reason()).isEqualTo(reason);
                      });
            });
  }

  @Test
  void birthDate_onThe14thBirthday_isAccepted() {
    assertThat(service.signUp(requestWithBirthDate("2012-10-27")).userId()).isNotNull();
  }

  @Test
  void birthDate_theDayBeforeThe14thBirthday_isRejected() {
    assertRejected("2012-10-28", "만 14세 이상만 가입할 수 있습니다.");
  }

  @Test
  void birthDate_today_isRejectedAsNotPast() {
    assertRejected("2026-10-27", "과거 날짜여야 합니다.");
  }

  @Test
  void birthDate_future_isRejected() {
    assertRejected("2027-01-01", "과거 날짜여야 합니다.");
  }

  @Test
  void birthDate_yesterday_isRejectedAsUnder14() {
    assertRejected("2026-10-26", "만 14세 이상만 가입할 수 있습니다.");
  }

  @Test
  void birthDate_before1900_isRejected() {
    assertRejected("1899-12-31", "1900-01-01 이후여야 합니다.");
  }

  @Test
  void birthDate_on19000101_isAccepted() {
    assertThat(service.signUp(requestWithBirthDate("1900-01-01")).userId()).isNotNull();
  }
}
