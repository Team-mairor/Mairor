package com.mairor.backend.analysis.extraction;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class StepTimeTest {

  @ParameterizedTest
  @CsvSource({
    "00:00, 0",
    "03:22, 202",
    "30:58, 1858",
    "62:05, 3725",
    "1:02:05, 3725",
    "00:12.5, 12.5"
  })
  void parsesMinutesAndSeconds(String value, double expected) {
    assertThat(StepTime.parse(value)).isEqualTo(expected);
  }

  @ParameterizedTest
  @NullAndEmptySource
  @ValueSource(strings = {"322", "03:75", "1:60:00", "aa:bb", "-01:00", "1:2:3:4"})
  void wrongFormatIsNull(String value) {
    assertThat(StepTime.parse(value)).isNull();
  }
}
