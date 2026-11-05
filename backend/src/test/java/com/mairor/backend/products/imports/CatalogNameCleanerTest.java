package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

class CatalogNameCleanerTest {

  // --- 상품명 ---

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      value = {
        "[NEW] 쥬시 래스팅 틴트|쥬시 래스팅 틴트",
        "쥬시 래스팅 틴트 [BEST]|쥬시 래스팅 틴트",
        "[NEW] [HOT] 쥬시 래스팅 틴트 [BEST]|쥬시 래스팅 틴트",
        "  [HOT]쥬시 래스팅 틴트  |쥬시 래스팅 틴트",
        "쥬시 [NEW] 래스팅 틴트|쥬시 [NEW] 래스팅 틴트"
      })
  void productNameLosesOnlyLeadingAndTrailingBadges(String raw, String expected) {
    assertThat(CatalogNameCleaner.cleanProductName(raw)).isEqualTo(expected);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "쥬시 래스팅 틴트 세트",
        "쥬시 래스팅 틴트 1+1",
        "[기획] 쥬시 래스팅 틴트",
        "쥬시 래스팅 틴트 리필",
        "쥬시 래스팅 틴트 5.5g",
        "[한정] 쥬시 래스팅 틴트",
        "쥬시 래스팅 틴트 (증정)",
        "[new] 쥬시 래스팅 틴트"
      })
  void productNameKeepsWhatDistinguishesAnotherProduct(String raw) {
    assertThat(CatalogNameCleaner.cleanProductName(raw)).isEqualTo(raw);
  }

  @Test
  void productNameThatIsOnlyABadgeIsKept() {
    assertThat(CatalogNameCleaner.cleanProductName(" [NEW] ")).isEqualTo("[NEW]");
  }

  // --- 호수명 ---

  @ParameterizedTest
  @CsvSource(
      delimiter = '|',
      value = {
        "[NEW] 01 단팥 브라운|01 단팥 브라운",
        "[BEST]01 단팥 브라운|01 단팥 브라운",
        "[HOT] 01 단팥 브라운|01 단팥 브라운",
        "[공식몰 단독] 01 단팥 브라운|01 단팥 브라운",
        "[일반] 01 단팥 브라운|01 단팥 브라운",
        "[CU콜라보] 01 단팥 브라운|01 단팥 브라운",
        "01 단팥 브라운 +추가2종증정|01 단팥 브라운",
        "01 단팥 브라운+추가10종증정|01 단팥 브라운",
        "[NEW] [공식몰 단독] 01 단팥 브라운 +추가3종증정|01 단팥 브라운"
      })
  void shadeNameLosesOnlyConfirmedPhrases(String raw, String expected) {
    assertThat(CatalogNameCleaner.cleanShadeName(raw)).isEqualTo(expected);
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "[한정 매트] 01 단팥 브라운",
        "[콜라보 전용색] 01 단팥 브라운",
        "[증정용 미니] 01 단팥 브라운",
        "[리필] 01 단팥 브라운",
        "[매트] 01 단팥 브라운",
        "01 단팥 브라운 (NEW)",
        "01 단팥 브라운 (증정)",
        "01+02",
        "01 단팥 브라운 +추가종증정",
        "01 단팥 브라운 +추가2종 증정",
        "01 단팥 브라운 [NEW]",
        "[new] 01 단팥 브라운"
      })
  void shadeNameKeepsAnythingThatIsNotAnExactConfirmedPhrase(String raw) {
    assertThat(CatalogNameCleaner.cleanShadeName(raw)).isEqualTo(raw);
  }

  @Test
  void shadeNameThatWouldBecomeEmptyIsKept() {
    assertThat(CatalogNameCleaner.cleanShadeName("[일반]")).isEqualTo("[일반]");
    // 앞 배지와 뒤 증정 문구를 모두 지우면 이름이 남지 않으므로 지우지 않는다
    assertThat(CatalogNameCleaner.cleanShadeName("[NEW] +추가2종증정")).isEqualTo("[NEW] +추가2종증정");
  }

  @Test
  void removablePhraseIsDetectedSoThePlainOptionCanBeTheRepresentative() {
    assertThat(CatalogNameCleaner.hasRemovablePhrase("[NEW] 01 코랄")).isTrue();
    assertThat(CatalogNameCleaner.hasRemovablePhrase("01 코랄 +추가2종증정")).isTrue();
    assertThat(CatalogNameCleaner.hasRemovablePhrase("01 코랄")).isFalse();
    assertThat(CatalogNameCleaner.hasRemovablePhrase("[한정 매트] 01 코랄")).isFalse();
  }

  // --- 호수 비교 키 ---

  @Test
  void optionsWithAndWithoutConfirmedPhrasesShareOneComparisonKey() {
    String plain = CatalogNameCleaner.shadeComparisonKey("01 단팥 브라운");

    assertThat(CatalogNameCleaner.shadeComparisonKey("[NEW] 01 단팥 브라운")).isEqualTo(plain);
    assertThat(CatalogNameCleaner.shadeComparisonKey("[공식몰 단독]01 단팥  브라운")).isEqualTo(plain);
    assertThat(CatalogNameCleaner.shadeComparisonKey("01 단팥 브라운 +추가2종증정")).isEqualTo(plain);
    assertThat(CatalogNameCleaner.shadeComparisonKey(" 01 단팥 브라운 ")).isEqualTo(plain);
    assertThat(plain).isEqualTo("01 단팥 브라운");
  }

  @Test
  void unconfirmedMarkersKeepOptionsApart() {
    String plain = CatalogNameCleaner.shadeComparisonKey("01 코랄");

    assertThat(CatalogNameCleaner.shadeComparisonKey("[한정 매트] 01 코랄")).isNotEqualTo(plain);
    assertThat(CatalogNameCleaner.shadeComparisonKey("01 코랄 (미니)")).isNotEqualTo(plain);
    assertThat(CatalogNameCleaner.shadeComparisonKey("01+02")).isNotEqualTo("01");
  }

  @Test
  void comparisonKeyOfABlankNameIsRejected() {
    assertThatThrownBy(() -> CatalogNameCleaner.shadeComparisonKey("   "))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
