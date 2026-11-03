package com.mairor.backend.products.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.text.Normalizer;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

class CatalogTextNormalizerTest {

  // 포매터가 유니코드 이스케이프를 눈에 안 보이는 실제 문자로 바꾸므로 코드값으로 만든다
  private static final String NBSP = Character.toString(0x00A0);
  private static final String IDEOGRAPHIC_SPACE = Character.toString(0x3000);
  private static final String CAPITAL_I_WITH_DOT = Character.toString(0x0130);
  private static final String COMBINING_DOT_ABOVE = Character.toString(0x0307);

  @Test
  void decomposedHangulIsComposedSoBothFormsGiveTheSameKey() {
    String composed = "에뛰드";
    String decomposed = Normalizer.normalize(composed, Normalizer.Form.NFD);

    assertThat(decomposed).isNotEqualTo(composed);
    assertThat(CatalogTextNormalizer.normalize(decomposed))
        .isEqualTo(CatalogTextNormalizer.normalize(composed))
        .isEqualTo("에뛰드");
  }

  @Test
  void leadingAndTrailingUnicodeWhitespaceIsRemoved() {
    // NBSP 는 String.strip() 이 지우지 않는 공백이라 따로 확인한다
    String text = NBSP + IDEOGRAPHIC_SPACE + "\t 디어달링 틴트 \n" + NBSP;

    assertThat(CatalogTextNormalizer.normalize(text)).isEqualTo("디어달링 틴트");
  }

  @Test
  void whitespaceRunsInsideAreCollapsedToOneAsciiSpace() {
    String text = "1호" + NBSP + NBSP + "오렌지\t" + IDEOGRAPHIC_SPACE + "레드";

    assertThat(CatalogTextNormalizer.normalize(text)).isEqualTo("1호 오렌지 레드");
  }

  @Test
  void lettersAreLowercasedWithTheRootLocale() {
    assertThat(CatalogTextNormalizer.normalize("ETUDE Dear DARLING"))
        .isEqualTo("etude dear darling");
  }

  @Test
  void dottedCapitalIBecomesTwoCharactersUnderTheRootLocale() {
    // Locale.ROOT 에서 'İ'(U+0130) 는 'i' + 결합 점(U+0307) 두 글자가 된다. 그래서 정규화 컬럼 길이를 원문의 두 배로 잡는다
    assertThat(CatalogTextNormalizer.normalize(CAPITAL_I_WITH_DOT))
        .isEqualTo("i" + COMBINING_DOT_ABOVE)
        .hasSize(2);
    // 대문자 'I' 는 터키어 로케일의 점 없는 'ı' 가 아니라 'i' 가 된다
    assertThat(CatalogTextNormalizer.normalize("TINT")).isEqualTo("tint");
  }

  @Test
  void sharpSIsKeptBecauseOnlyLowercasingIsApplied() {
    // 대소문자 접기(case folding)가 아니라 소문자화만 하므로 ß 와 ss 는 다른 키다
    assertThat(CatalogTextNormalizer.normalize("Straße")).isEqualTo("straße");
    assertThat(CatalogTextNormalizer.normalize("STRASSE")).isEqualTo("strasse");
  }

  @Test
  void normalizingTwiceGivesTheSameResult() {
    String once = CatalogTextNormalizer.normalize(" Water  Gel" + NBSP + "TINT ");

    assertThat(CatalogTextNormalizer.normalize(once)).isEqualTo(once).isEqualTo("water gel tint");
  }

  static Stream<String> blankTexts() {
    return Stream.of("", " ", "\t\n", NBSP, IDEOGRAPHIC_SPACE + IDEOGRAPHIC_SPACE);
  }

  @ParameterizedTest
  @MethodSource("blankTexts")
  void emptyOrWhitespaceOnlyTextIsRejected(String text) {
    assertThatThrownBy(() -> CatalogTextNormalizer.normalize(text))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void nullIsRejected() {
    assertThatThrownBy(() -> CatalogTextNormalizer.normalize(null))
        .isInstanceOf(NullPointerException.class);
  }
}
