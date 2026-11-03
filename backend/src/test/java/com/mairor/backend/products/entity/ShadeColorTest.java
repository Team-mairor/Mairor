package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class ShadeColorTest {

  @Test
  void lowercaseHexIsStoredInUppercase() {
    ShadeColor color = ShadeColor.of("#e8452c", "OFFICIAL", true);

    assertThat(color.getHex()).isEqualTo("#E8452C");
    assertThat(color.getSource()).isEqualTo("OFFICIAL");
    assertThat(color.isEstimated()).isTrue();
  }

  @ParameterizedTest
  @ValueSource(strings = {"E8452C", "#E8452", "#E8452CC", "#G8452C", "#e8 52c", ""})
  void malformedHexIsRejected(String hex) {
    assertThatThrownBy(() -> ShadeColor.of(hex, "OFFICIAL", false))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void blankOrTooLongSourceIsRejected() {
    assertThatThrownBy(() -> ShadeColor.of("#E8452C", " ", false))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(
            () -> ShadeColor.of("#E8452C", "a".repeat(ShadeColor.SOURCE_MAX_LENGTH + 1), false))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void colorsWithTheSameValuesAreEqual() {
    assertThat(ShadeColor.of("#e8452c", "OFFICIAL", false))
        .isEqualTo(ShadeColor.of("#E8452C", "OFFICIAL", false))
        .isNotEqualTo(ShadeColor.of("#E8452C", "OFFICIAL", true));
  }
}
