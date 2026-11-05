package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

import org.junit.jupiter.api.Test;

class ColorDifferenceTest {

  /** Sharma, Wu, Dalal(2005)이 공개한 CIEDE2000 검증 값. 구현이 표준 공식과 같은지 본다. */
  @Test
  void matchesTheReferenceValuesOfTheCiede2000Paper() {
    assertThat(ColorDifference.deltaE2000(50, 2.6772, -79.7751, 50, 0, -82.7485))
        .isCloseTo(2.0425, within(0.0001));
    assertThat(ColorDifference.deltaE2000(50, 3.1571, -77.2803, 50, 0, -82.7485))
        .isCloseTo(2.8615, within(0.0001));
    assertThat(ColorDifference.deltaE2000(50, 2.8361, -74.0200, 50, 0, -82.7485))
        .isCloseTo(3.4412, within(0.0001));
    assertThat(ColorDifference.deltaE2000(50, -1.3802, -84.2814, 50, 0, -82.7485))
        .isCloseTo(1.0000, within(0.0001));
    assertThat(ColorDifference.deltaE2000(50, 2.5, 0, 50, 0, -2.5))
        .isCloseTo(4.3065, within(0.0001));
    assertThat(ColorDifference.deltaE2000(50, 2.5, 0, 73, 25, -18))
        .isCloseTo(27.1492, within(0.0001));
    assertThat(ColorDifference.deltaE2000(60.2574, -34.0099, 36.2677, 60.4626, -34.1751, 39.4387))
        .isCloseTo(1.2644, within(0.0001));
  }

  @Test
  void sameColorIsZeroAndIsSymmetric() {
    assertThat(ColorDifference.deltaE2000("#D9B8A0", "#d9b8a0")).isZero();
    assertThat(ColorDifference.deltaE2000("#D9B8A0", "#B76E79"))
        .isCloseTo(ColorDifference.deltaE2000("#B76E79", "#D9B8A0"), within(1e-9));
  }

  @Test
  void blackAndWhiteAreAboutOneHundredApartAndSimilarColorsAreClose() {
    assertThat(ColorDifference.deltaE2000("#000000", "#FFFFFF")).isCloseTo(100.0, within(0.5));
    assertThat(ColorDifference.deltaE2000("#C9707A", "#CA717B")).isLessThan(1.0);
    assertThat(ColorDifference.deltaE2000("#C9707A", "#4A3427")).isGreaterThan(20.0);
  }

  @Test
  void malformedHexIsRejected() {
    assertThatThrownBy(() -> ColorDifference.deltaE2000("D9B8A0", "#D9B8A0"))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> ColorDifference.deltaE2000("#D9B8A0", null))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
